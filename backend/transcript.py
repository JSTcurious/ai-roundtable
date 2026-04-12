"""
backend/transcript.py

Shared conversation history for a roundtable session.

The transcript is the product. Every model receives the complete
verbatim history on every call. Sequential Round 1 means each
model has heard what came before it — this compounding effect
is the core product differentiator. Never call models in parallel.

Classes:
    Transcript  — append-only conversation log with per-model history views
"""

from datetime import datetime


class Transcript:
    """
    Append-only log of all messages in a roundtable session.

    Roles:
        "user"      — the human
        "assistant" — any model response (labeled by sender)

    Round labels:
        "round1"    — initial responses from Claude, Gemini, GPT
        "audit"     — Perplexity fact-check findings (deferred to v2.1)
        "critique"  — deep mode cross-critique round (deferred to v2.1)
        "synthesis" — Claude final synthesis
    """

    def __init__(self):
        self.messages = []
        self.session_config = None
        self.intake_summary = None

    def add_user_message(self, content: str):
        """Append a user message to the transcript."""
        self.messages.append({
            "role": "user",
            "sender": "You",
            "content": content,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        })

    def add_model_message(self, sender: str, content: str, round: str = "round1"):
        """
        Append a model response to the transcript.

        Args:
            sender:  "Claude" | "Gemini" | "GPT" | "Perplexity"
            content: full response text
            round:   "round1" | "audit" | "critique" | "synthesis"
        """
        self.messages.append({
            "role": "assistant",
            "sender": sender,
            "content": content,
            "round": round,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        })

    def get_history_for_model(self, model_name: str) -> list:
        """
        Return the full conversation history formatted for a model's API.

        Every model receives the complete history. Model responses are
        prefixed with the sender name so each model knows who said what.
        User messages are passed through as-is.

        Returns list of {"role": "user"|"assistant", "content": str} dicts.
        """
        history = []
        for msg in self.messages:
            if msg["role"] == "user":
                history.append({
                    "role": "user",
                    "content": msg["content"],
                })
            else:
                history.append({
                    "role": "assistant",
                    "content": f"{msg['sender']}: {msg['content']}",
                })
        return history

    def get_round1_responses(self) -> dict:
        """
        Return all Round 1 model responses keyed by lowercase sender name.
        Used to pass context to the Perplexity audit (v2.1) and synthesis.

        Returns: {"claude": str, "gemini": str, "gpt": str}
        """
        responses = {}
        for msg in self.messages:
            if msg.get("round") == "round1" and msg["role"] == "assistant":
                responses[msg["sender"].lower()] = msg["content"]
        return responses

    def get_messages_by_round(self, round: str) -> list:
        """
        Return all messages for a specific round label.

        Args:
            round: "round1" | "audit" | "critique" | "synthesis"
        """
        return [m for m in self.messages if m.get("round") == round]

    def to_dict(self) -> dict:
        """
        Return the full transcript as a serialisable dict.
        Used by the exporter to generate markdown output.
        """
        return {
            "messages": self.messages,
            "session_config": self.session_config,
            "intake_summary": self.intake_summary,
        }
