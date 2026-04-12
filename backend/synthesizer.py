"""
backend/synthesizer.py

Claude synthesis prompt builder for ai-roundtable v2.

After Round 1 (Claude, Gemini, GPT) and the Perplexity audit,
Claude synthesizes all inputs into a final deliverable that
matches the output_type declared during intake.

Claude's synthesis role:
    - Incorporates the strongest reasoning from each model
    - Corrects factual errors Perplexity identified
    - Surfaces disagreements explicitly and explains what they mean
    - Produces a structured output matching the declared output_type
    - Does NOT summarize — synthesizes

Functions:
    build_synthesis_messages(transcript, session_config)
        — constructs the messages list for the Claude synthesis call
    extract_disagreements(round1_responses)
        — identifies explicit disagreements across model responses
          for surfacing in the synthesis
"""

from backend.transcript import Transcript


def build_synthesis_messages(transcript: Transcript, session_config: dict) -> list:
    """
    Construct the messages list to pass to Claude for synthesis.

    Includes:
        - Full conversation history
        - Round 1 responses from Claude, Gemini, GPT
        - Perplexity audit findings
        - Output type from session_config to shape the synthesis structure

    Args:
        transcript: the current session's Transcript
        session_config: the dict produced by IntakeSession on completion

    Returns list of {"role": str, "content": str} dicts for the Claude API.
    """
    pass


def extract_disagreements(round1_responses: dict) -> list[str]:
    """
    Identify and return explicit points of disagreement across
    Claude, Gemini, and GPT Round 1 responses.

    Used to populate the "Where Models Disagreed" section
    of the synthesis and the markdown export.

    Args:
        round1_responses: {"claude": str, "gemini": str, "gpt": str}

    Returns list of disagreement descriptions.
    """
    pass
