"""
backend/privacy_guard.py — ingress PII tokenization and local re-hydration.

Spec: docs/PRIVACY_SECURITY_SPEC.md (Phase 1, §4.1).

Sensitive values in user text (emails, secrets, IDs, phone numbers, currency
amounts, private org names and person names) are replaced with numbered
placeholders such as [PERSON_1] before any text reaches a model provider. The
mapping lives only in a PrivacyVault held in server RAM for one user session;
rehydrate() swaps the originals back in for every frame sent to the client.

The vault is never serialized into a prompt, a log line or a client frame.
Detection is deterministic (regex + word lists in privacy_allowlist.json) and
errs toward keeping public context: allowlisted names (AWS, Google, SOC 2…)
are never tokenized so research and fact-checking still work.

Boundary rule: sanitize everything that comes from the client, rehydrate
everything that goes back to it. Model calls in between only ever see tokens.
"""

from __future__ import annotations

import json
import re
import threading
import time
from decimal import ROUND_HALF_UP, Decimal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

# ── Word lists ───────────────────────────────────────────────────────────────

_LISTS = json.loads((Path(__file__).parent / "privacy_allowlist.json").read_text())
PUBLIC_NAMES: frozenset[str] = frozenset(_LISTS["public_names"])
GIVEN_NAMES: frozenset[str] = frozenset(_LISTS["given_names"])
COMMON_WORDS: frozenset[str] = frozenset(_LISTS["common_words"])

# ── Token syntax ─────────────────────────────────────────────────────────────

# [TYPE_n] with an optional magnitude hint for amounts: [AMOUNT_1 ≈ $440K]
TOKEN_PATTERN = r"\[[A-Z]+_\d+(?:\s*≈[^\]\n]{0,40})?\]"
_TOKEN_RE = re.compile(r"\[(?P<kind>[A-Z]+)_(?P<num>\d+)(?:\s*≈[^\]\n]{0,40})?\]")
# A trailing fragment that could still grow into a token: "[", "[ORG_", "[AMOUNT_1 ≈ $4"
_PARTIAL_TOKEN_RE = re.compile(r"\[(?:[A-Z]+(?:_(?:\d+(?:\s*(?:≈[^\]\n]*)?)?)?)?)?$")
_MAX_HELD = 64

# ── Control characters (shared with intake.sanitize_text and the evidence sandbox)

_CONTROL_RE = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff"
    "\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)


def strip_control_chars(text: str) -> str:
    """Remove bidi overrides, zero-width marks and C0 controls (keeps \\t \\n \\r)."""
    if not isinstance(text, str):
        return text
    return _CONTROL_RE.sub("", text)


# ── Vault ────────────────────────────────────────────────────────────────────

@dataclass(repr=False)
class PrivacyVault:
    """Per-session token map. RAM only; never sent to a model or the client."""

    token_map: dict = field(default_factory=dict)  # "[ORG_1]" -> "Apex Logistics"
    reverse: dict = field(default_factory=dict)    # "Apex Logistics" -> "[ORG_1]" (display form)
    counters: dict = field(default_factory=dict)   # "ORG" -> 1

    def token_for(self, kind: str, value: str, hint: str = "") -> str:
        """Return the token for value, creating the next numbered one if new."""
        existing = self.reverse.get(value)
        if existing:
            return existing
        n = self.counters.get(kind, 0) + 1
        self.counters[kind] = n
        canonical = f"[{kind}_{n}]"
        display = f"[{kind}_{n} ≈ {hint}]" if hint else canonical
        self.token_map[canonical] = value
        self.reverse[value] = display
        return display

    def audit(self) -> dict:
        """Counts only — safe to send to the client."""
        return {
            "pii_tokens_redacted": len(self.token_map),
            "by_type": dict(self.counters),
        }

    def clear(self) -> None:
        self.token_map.clear()
        self.reverse.clear()
        self.counters.clear()

    def __repr__(self) -> str:  # never print values
        return f"PrivacyVault(tokens={len(self.token_map)})"


class VaultStore:
    """
    Holds vaults between the intake HTTP calls and the session WebSocket.

    Keyed by an opaque privacy_ref (the intake session id). Entries expire
    after ttl_seconds; the WebSocket take()s its vault, after which it lives
    only in that connection's scope.
    """

    def __init__(self, ttl_seconds: float = 1800, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._clock = clock
        self._items: dict[str, tuple[float, PrivacyVault]] = {}
        self._lock = threading.Lock()

    def _sweep(self) -> None:
        cutoff = self._clock() - self._ttl
        for key in [k for k, (t, _) in self._items.items() if t < cutoff]:
            self._items.pop(key)[1].clear()

    def put(self, ref: str, vault: PrivacyVault) -> None:
        with self._lock:
            self._sweep()
            self._items[ref] = (self._clock(), vault)

    def get(self, ref: Optional[str]) -> Optional[PrivacyVault]:
        if not ref:
            return None
        with self._lock:
            self._sweep()
            item = self._items.get(ref)
            if item is None:
                return None
            self._items[ref] = (self._clock(), item[1])  # touch
            return item[1]

    def take(self, ref: Optional[str]) -> Optional[PrivacyVault]:
        if not ref:
            return None
        with self._lock:
            self._sweep()
            item = self._items.pop(ref, None)
            return item[1] if item else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


VAULTS = VaultStore()

# ── Detection rules ──────────────────────────────────────────────────────────

_CAP = r"[A-Z][\w&'’.-]*"  # a capitalized word, incl. acronyms and Co-Names

_ORG_SUFFIXES = (
    "Inc", "LLC", "L\\.L\\.C\\.", "Ltd", "Limited", "Corp", "Corporation", "GmbH", "AG", "PLC", "LLP", "LP",
    "Logistics", "Labs", "Partners", "Group", "Holdings", "Capital", "Ventures", "Technologies", "Analytics",
    "Consulting", "Associates", "Industries", "Enterprises", "Pharmaceuticals", "Therapeutics", "Robotics", "Bank",
)
_ORG_SUFFIX_SET = frozenset(s.replace("\\", "") for s in _ORG_SUFFIXES)

_ORG_CUES = (
    r"offer\s+from", r"offer\s+at", r"work(?:s|ed|ing)?\s+(?:at|for)", r"employed\s+by", r"hired\s+by",
    r"acquired\s+by", r"join(?:s|ed|ing)?", r"leav(?:e|es|ing)", r"left", r"quit(?:ting)?", r"at",
    r"(?:my|our|the)\s+(?:employer|company|startup|firm|client|customer|vendor)",
)

_ROLE_WORDS = (
    "manager", "boss", "wife", "husband", "partner", "spouse", "son", "daughter", "mother", "father", "mom",
    "dad", "brother", "sister", "friend", "colleague", "coworker", "co-worker", "cofounder", "co-founder",
    "lawyer", "attorney", "doctor", "recruiter", "landlord", "tenant", "mentor", "advisor", "skip-level",
    "director", "lead", "report", "hiring manager", "sponsor",
)

# Given names as an alternation so "Then Marcus Bell" still finds "Marcus Bell"
# (a generic [A-Z][a-z]+ pair would consume "Then Marcus" and skip past it).
_GIVEN_ALT = "|".join(sorted((re.escape(n) for n in GIVEN_NAMES), key=len, reverse=True))

_CURRENCY_CODES = r"USD|EUR|GBP|CAD|AUD|INR|JPY|CHF|SGD|CNY"
_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
}
AMOUNT_MIN = 1000  # Q2 decision: smaller amounts are not tokenized


@dataclass(frozen=True)
class _Rule:
    kind: str
    regex: re.Pattern
    # Given the match, return (start, end) of the value to tokenize or None to skip.
    select: Callable[[re.Match], Optional[tuple[int, int]]]
    hint: Optional[Callable[[str], str]] = None


def _whole(m: re.Match) -> tuple[int, int]:
    return m.start("v"), m.end("v")


def _is_public(candidate: str) -> bool:
    if candidate in PUBLIC_NAMES:
        return True
    words = candidate.split()
    if words and words[0] in PUBLIC_NAMES:
        return True
    if words and words[-1] in _ORG_SUFFIX_SET and " ".join(words[:-1]) in PUBLIC_NAMES:
        return True
    return False


def _trim_run(m: re.Match, keep_interior: bool = False) -> Optional[tuple[int, int]]:
    """
    Shrink a run of capitalized words to the plausible name: drop leading
    common words, strip trailing punctuation and possessives, and stop at the
    first common word after the name has started. Returns None if nothing
    private is left.

    keep_interior=True is for runs anchored by a company suffix ("Apex Health
    Group"): the suffix says the whole run is the name, so a common word in
    the middle ("Health") does not end it.
    """
    start, end = m.start("v"), m.end("v")
    text = m.string
    words = [(w.start() + start, w.end() + start) for w in re.finditer(r"\S+", text[start:end])]

    def clean(span):
        s, e = span
        while e > s and text[e - 1] in ".,;:!?'’-":
            e -= 1
        if text[s:e].endswith(("'s", "’s")):
            e -= 2
        return s, e

    words = [clean(w) for w in words]
    while words and text[words[0][0]:words[0][1]] in COMMON_WORDS:
        words.pop(0)
    kept = []
    for w in words:
        if text[w[0]:w[1]] in COMMON_WORDS and not keep_interior:
            break
        kept.append(w)
    if not kept:
        return None
    s, e = kept[0][0], kept[-1][1]
    candidate = text[s:e]
    if not candidate or _is_public(candidate):
        return None
    return s, e


def _org_suffix_select(m: re.Match) -> Optional[tuple[int, int]]:
    span = _trim_run(m, keep_interior=True)
    if span is None:
        return None
    candidate = m.string[span[0]:span[1]]
    words = candidate.split()
    # Need at least one real name word before the suffix.
    if len(words) < 2 and words[-1].rstrip(".") in _ORG_SUFFIX_SET:
        return None
    return span


def _first_last_select(m: re.Match) -> Optional[tuple[int, int]]:
    first, last = m.group("first"), m.group("last")
    if first not in GIVEN_NAMES:
        return None
    if last in COMMON_WORDS or last in PUBLIC_NAMES or last in _ORG_SUFFIX_SET:
        return None
    if _is_public(f"{first} {last}"):
        return None
    return m.start("v"), m.end("v")


def _amount_value(raw: str) -> Optional[float]:
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z]+)?", raw)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    if unit in _MULTIPLIERS:
        value *= _MULTIPLIERS[unit]
    return value


def _amount_select(m: re.Match) -> Optional[tuple[int, int]]:
    value = _amount_value(m.group("v"))
    if value is None or value < AMOUNT_MIN:
        return None
    return _whole(m)


def _round_sig(value: float, digits: int) -> float:
    """Round half-up to significant digits (185,000 -> 190,000; %g would give 180,000)."""
    if value <= 0:
        return 0.0
    d = Decimal(str(value))
    quantum = Decimal(1).scaleb(d.adjusted() - digits + 1)
    return float(d.quantize(quantum, rounding=ROUND_HALF_UP))


def _amount_hint(raw: str) -> str:
    """Coarse magnitude (2 significant figures): $437,500 -> $440K."""
    value = _amount_value(raw) or 0
    prefix_m = re.match(rf"\s*((?:{_CURRENCY_CODES})\s?|[$€£¥₹])", raw)
    prefix = prefix_m.group(1) if prefix_m else ""
    if prefix.strip() and prefix.strip().isalpha():
        prefix = prefix.strip() + " "
    rounded = _round_sig(value, 2)
    for scale, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if rounded >= scale:
            return f"{prefix}{rounded / scale:g}{suffix}"
    return f"{prefix}{rounded:g}"


def _digits_at_least(n: int):
    def select(m: re.Match):
        if sum(c.isdigit() for c in m.group("v")) < n:
            return None
        return _whole(m)
    return select


def _id_with_digit(m: re.Match):
    value = m.group("v")
    if not any(c.isdigit() for c in value):
        return None
    # A bare number after a generic label ("case 2026", "order 10000") needs an
    # explicit marker: "#", ":", "no", "number".
    if value.isdigit():
        label = m.string[m.start():m.start("v")].lower()
        if not re.search(r"[#:]|\b(?:no|number|num)\b", label):
            return None
    return _whole(m)


def _prefixed_id_select(m: re.Match):
    if _is_public(m.group("v")) or m.group("v").split("-")[0] in PUBLIC_NAMES:
        return None
    return _whole(m)


def _c(pattern: str, flags: int = 0) -> re.Pattern:
    return re.compile(pattern, flags)


_AMOUNT_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_AMOUNT_UNIT = r"(?:\s?(?:[kKmMbB]|mm|MM|mn|bn|BN|thousand|million|billion))?(?![\w])"

RULES: tuple[_Rule, ...] = (
    _Rule("SECRET", _c(
        r"(?P<v>\bsk-ant-[\w-]{10,}|\bsk-(?:proj-)?[\w-]{16,}|\bxai-[A-Za-z0-9]{16,}|\bpplx-[A-Za-z0-9]{16,}"
        r"|\bAIza[\w-]{30,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_\w{20,}|\bAKIA[0-9A-Z]{16}\b"
        r"|\bxox[baprs]-[\w-]{10,}|\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"
        r"|(?<=Bearer )[\w.~+/-]{16,}=*)"), _whole),
    _Rule("EMAIL", _c(r"(?P<v>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"), _whole),
    # Labeled identifiers: replace only the value after the label.
    _Rule("ID", _c(
        r"(?i:\b(?:acct|account|policy|contract|invoice|case|claim|member|employee|order|ticket|ref|reference"
        r"|loan|routing|passport|license|licence|id)\b\.?\s*(?:no\.?|number|num|#|id)?\s*[:#]?\s*)"
        r"(?P<v>(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,})\b"), _id_with_digit),
    _Rule("ID", _c(r"(?P<v>\b\d{3}-\d{2}-\d{4}\b)"), _whole),                        # SSN
    _Rule("ID", _c(r"(?P<v>\b\d{2}-\d{7}\b)"), _whole),                              # EIN
    _Rule("ID", _c(r"(?P<v>\b(?:EAC|WAC|LIN|SRC|IOE|MSC|NBC|YSC)\d{10}\b)"), _whole),  # USCIS receipt
    _Rule("ID", _c(r"(?P<v>\bA-?\d{8,9}\b)"), _whole),                               # A-number
    _Rule("ID", _c(r"(?P<v>\b(?:\d{4}[ -]){3}\d{1,4}\b)"), _whole),                  # card-like
    _Rule("ID", _c(r"(?P<v>\b[A-Z]{2,6}-\d{3,}[A-Z0-9-]*\b)"), _prefixed_id_select),  # MSA-88412
    _Rule("PHONE", _c(r"(?P<v>(?<![\w+])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\w))"),
          _digits_at_least(10)),
    _Rule("PHONE", _c(r"(?P<v>(?<!\w)\+\d{1,3}(?:[\s.-]?\d){7,14}(?!\w))"), _digits_at_least(8)),
    _Rule("AMOUNT", _c(
        rf"(?P<v>(?:[$€£¥₹]\s?|\b(?:{_CURRENCY_CODES})\s?){_AMOUNT_NUM}{_AMOUNT_UNIT}"
        rf"|\b{_AMOUNT_NUM}{_AMOUNT_UNIT}\s?(?:dollars|euros|pounds|rupees|(?:{_CURRENCY_CODES})\b))"),
        _amount_select, _amount_hint),
    # Org: capitalized run ending in a company suffix.
    _Rule("ORG", _c(
        rf"(?P<v>(?:{_CAP}[ \t]+){{1,4}}(?:{'|'.join(_ORG_SUFFIXES)})\b\.?)"), _org_suffix_select),
    # Org: capitalized run after an employment cue.
    _Rule("ORG", _c(
        rf"(?i:\b(?:{'|'.join(_ORG_CUES)})[ \t]+)(?P<v>{_CAP}(?:[ \t]+{_CAP}){{0,3}})"), _trim_run),
    # Person: honorific + name.
    _Rule("PERSON", _c(
        rf"\b(?:Mr|Mrs|Ms|Mx|Dr|Prof|Professor|Judge)\.?[ \t]+(?P<v>[A-Z][a-z]+(?:[-'’][A-Z][a-z]+)?"
        rf"(?:[ \t]+[A-Z][a-z]+(?:[-'’][A-Z][a-z]+)?){{0,2}})"), _trim_run),
    # Person: "my manager Priya Raman", "our recruiter, Dan"
    _Rule("PERSON", _c(
        rf"(?i:\b(?:my|our|his|her|their)[ \t]+(?:{'|'.join(_ROLE_WORDS)}))[ \t]*,?[ \t]+"
        rf"(?P<v>[A-Z][a-z]+(?:[-'’][A-Z][a-z]+)?(?:[ \t]+[A-Z][a-z]+(?:[-'’][A-Z][a-z]+)?)?)"), _trim_run),
    # Person: known given name + capitalized surname (optional middle initial).
    _Rule("PERSON", _c(
        rf"(?P<v>\b(?P<first>{_GIVEN_ALT})[ \t]+(?:[A-Z]\.[ \t]+)?"
        r"(?P<last>[A-Z][a-z]+(?:[-'’][A-Z][a-z]+)?))\b"), _first_last_select),
)

_PROTECTED = {
    id(rule): re.compile(rf"(?P<_tok>{TOKEN_PATTERN})|{rule.regex.pattern}", rule.regex.flags)
    for rule in RULES
}

# ── Public API ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SanitizeResult:
    sanitized_text: str
    redaction_count: int  # replacements made in this call


def _replace_known(text: str, vault: PrivacyVault) -> tuple[str, int]:
    """Replace values the vault already knows (longest first), outside tokens."""
    count = 0
    for value in sorted(vault.reverse, key=len, reverse=True):
        if value not in text:
            continue
        token = vault.reverse[value]
        pattern = re.compile(rf"(?P<_tok>{TOKEN_PATTERN})|(?<!\w){re.escape(value)}(?!\w)")

        def repl(m, token=token):
            nonlocal count
            if m.group("_tok"):
                return m.group(0)
            count += 1
            return token

        text = pattern.sub(repl, text)
    return text, count


def sanitize(text: str, vault: PrivacyVault) -> SanitizeResult:
    """
    Replace sensitive values in text with tokens, recording them in vault.
    Existing tokens in text are left as they are.
    """
    if not isinstance(text, str) or not text:
        return SanitizeResult(text, 0)
    text, count = _replace_known(text, vault)

    for rule in RULES:
        pattern = _PROTECTED[id(rule)]

        def repl(m: re.Match, rule=rule) -> str:
            nonlocal count
            if m.group("_tok"):
                return m.group(0)
            span = rule.select(m)
            if span is None:
                return m.group(0)
            s, e = span
            value = m.string[s:e]
            if not value.strip():
                return m.group(0)
            hint = rule.hint(value) if rule.hint else ""
            token = vault.token_for(rule.kind, value, hint)
            count += 1
            return m.string[m.start():s] + token + m.string[e:m.end()]

        text = pattern.sub(repl, text)
    return SanitizeResult(text, count)


def sanitize_text(text: str, vault: PrivacyVault) -> str:
    return sanitize(text, vault).sanitized_text


def rehydrate(text: str, vault: "PrivacyVault | dict | None") -> str:
    """Swap known tokens back to their original values. Unknown tokens stay."""
    if not isinstance(text, str) or "[" not in text:
        return text
    token_map = vault.token_map if isinstance(vault, PrivacyVault) else (vault or {})
    if not token_map:
        return text

    def repl(m: re.Match) -> str:
        return token_map.get(f"[{m.group('kind')}_{m.group('num')}]", m.group(0))

    return _TOKEN_RE.sub(repl, text)


def _walk(obj: Any, fn: Callable[[str], str], skip_keys: Iterable[str] = ()) -> Any:
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        return {k: (v if k in skip_keys else _walk(v, fn, skip_keys)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v, fn, skip_keys) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_walk(v, fn, skip_keys) for v in obj)
    return obj


def sanitize_obj(obj: Any, vault: PrivacyVault, skip_keys: Iterable[str] = ()) -> Any:
    """Recursive sanitize over dict/list/str. Returns a new structure."""
    return _walk(obj, lambda s: sanitize(s, vault).sanitized_text, frozenset(skip_keys))


def rehydrate_obj(obj: Any, vault: "PrivacyVault | dict | None") -> Any:
    """Recursive rehydrate over dict/list/str. Returns a new structure."""
    return _walk(obj, lambda s: rehydrate(s, vault))


class StreamRehydrator:
    """
    Re-hydrates a text stream whose chunks may split a token ("[OR" + "G_1]").
    A trailing fragment that could still become a token is held until the
    next chunk; flush() releases whatever is left.
    """

    def __init__(self, vault: "PrivacyVault | dict | None"):
        self._vault = vault
        self._held = ""

    def feed(self, chunk: str) -> str:
        text = self._held + (chunk or "")
        self._held = ""
        cut = text.rfind("[")
        if cut != -1 and "]" not in text[cut:] and len(text) - cut <= _MAX_HELD:
            if _PARTIAL_TOKEN_RE.match(text, cut):
                self._held = text[cut:]
                text = text[:cut]
        return rehydrate(text, self._vault)

    def flush(self) -> str:
        text, self._held = self._held, ""
        return rehydrate(text, self._vault)

    def reset(self) -> None:
        self._held = ""

    @property
    def pending(self) -> bool:
        return bool(self._held)
