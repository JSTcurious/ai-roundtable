# app/router.py
# Parses @ mentions from your prompt
# Decides which models should respond each round

from typing import List

# Models available in the roundtable
AVAILABLE_MODELS = {
    "@llama": {
        "name": "Llama",
        "model_id": "Meta-Llama-3.1-405B-Instruct",
        "emoji": "🟣",
        "strength": "open source reasoning and broad knowledge"
    },
    "@gpt4omini": {
        "name": "GPT-4o Mini",
        "model_id": "gpt-4o-mini",
        "emoji": "🔵",
        "strength": "fast concise responses"
    },
    "@gpt4o": {
        "name": "GPT-4o",
        "model_id": "gpt-4o",
        "emoji": "🟢",
        "strength": "creative alternatives and structured output"
    }
}

def parse_mentions(prompt: str) -> List[dict]:
    """
    Extract @ mentions from prompt.
    Returns list of models that should respond.
    Order matters — @gpt4omini must be checked before @gpt4o
    to avoid partial matching.

    Examples:
        "@llama what are the risks?"        → [Llama]
        "@llama @gpt4o compare these"       → [Llama, GPT-4o]
        "@gpt4omini summarize everything"   → [GPT-4o Mini]
        "what do you think?"                → [] (no one called)
    """
    mentioned = []
    prompt_lower = prompt.lower()

    # AVAILABLE_MODELS is ordered: @gpt4omini before @gpt4o
    # This prevents @gpt4o matching inside @gpt4omini
    for mention, config in AVAILABLE_MODELS.items():
        if mention in prompt_lower:
            # Remove matched mention from prompt before checking next
            # Prevents @gpt4o matching after @gpt4omini already consumed it
            prompt_lower = prompt_lower.replace(mention, "", 1)
            mentioned.append(config)

    return mentioned

def get_system_prompt(model_name: str, all_models: List[str], strength: str) -> str:
    """
    System prompt for each model.
    Tells them who else is in the room and what they're good at.
    """
    others = [m for m in all_models if m != model_name]
    others_str = " and ".join(others) if others else "no one else"

    return (
        f"You are {model_name}, participating in a group roundtable discussion. "
        f"Your strength is {strength}. Lead with that. "
        f"Other participants in this roundtable are: {others_str}. "
        f"You can see everything said by everyone in the conversation history. "
        f"Respond only when directly addressed. "
        f"Be direct and concise. Build on what others have said when relevant. "
        f"Do not prefix your response with your own name."
    )