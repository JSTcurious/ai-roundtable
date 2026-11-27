"""
tests/test_dependency_pinning.py — DEPENDENCY_PINNING_SPEC AC1, AC5.

AC3 (WebSocket close paths on a real server) is tests/test_ws_close_paths.py.
The lock-in-sync half of AC1/AC4 is the CI lock check in
.github/workflows/tests.yml (it needs network access to resolve).
"""

import asyncio
import re
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "backend"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]+\])?==[^\s;]+")
KEY_PACKAGES = ("fastapi", "starlette", "uvicorn", "websockets",
                "anthropic", "openai", "google-genai")


def _requirement_lines(path: Path) -> list[str]:
    """Requirement lines only: no comments, hash or continuation lines."""
    return [
        line for line in path.read_text().splitlines()
        if line and not line.startswith(("#", " ", "\t", "-"))
    ]


def _names(path: Path) -> set[str]:
    return {re.split(r"[\[<>=!~; ]", line, maxsplit=1)[0].lower()
            for line in _requirement_lines(path)}


@pytest.mark.parametrize("locked,source", [
    ("requirements.txt", "requirements.in"),
    ("requirements-dev.txt", "requirements-dev.in"),
])
def test_ac1_lockfile_pins_every_package_and_records_command(locked, source):
    path = BACKEND / locked
    text = path.read_text()
    assert f"uv pip compile backend/{source}" in text  # uv's header
    assert "--generate-hashes" in text and "--python-version 3.13" in text
    lines = _requirement_lines(path)
    assert lines
    unpinned = [line for line in lines if not PIN.match(line)]
    assert unpinned == []
    # Every pin is hash-verified (pip enforces this for all or none).
    assert text.count("==") <= text.count("--hash=sha256:")


@pytest.mark.parametrize("locked,source", [
    ("requirements.txt", "requirements.in"),
    ("requirements-dev.txt", "requirements-dev.in"),
])
def test_ac1_every_direct_dependency_is_locked(locked, source):
    assert _names(BACKEND / source) <= _names(BACKEND / locked)


def test_ac1_dev_lock_includes_httpx_for_testclient():
    # starlette's TestClient needs httpx; openai 3.x / anthropic 2.x no longer
    # install it, so without this the WebSocket tests fail in a clean install.
    assert {"httpx", "pytest"} <= _names(BACKEND / "requirements-dev.txt")


def test_backend_never_imports_httpx():
    # httpx is a dev-only dependency now; importing it in app code crashes
    # the app on a Railway build (it nearly did in #51).
    offenders = [
        str(p.relative_to(BACKEND)) for p in BACKEND.rglob("*.py")
        if re.search(r"^\s*(import httpx|from httpx\b)", p.read_text(), re.M)
    ]
    assert offenders == []


def test_ac5_startup_logs_python_and_package_versions(capsys):
    from backend import main
    asyncio.run(main.startup_event())
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("[STARTUP] Python"))
    assert f"Python {sys.version.split()[0]}" in line
    for name in KEY_PACKAGES:
        assert f"{name} {version(name)}" in line
