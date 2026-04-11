# app/main.py
# ai-roundtable — v1
# A group chat where your contacts are AI models

import os
import streamlit as st
from openai import OpenAI
from transcript import Transcript
from router import parse_mentions, get_system_prompt, AVAILABLE_MODELS
from dotenv import load_dotenv

load_dotenv()

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ai-roundtable",
    page_icon="⬡",
    layout="centered"
)

# ── Styling ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Sora:wght@300;400;600&display=swap');

html, body, [class*="css"] { font-family: 'Sora', sans-serif; }
.stApp { background-color: #0d0d0d; color: #e8e8e8; }

.chat-row { margin-bottom: 1.2rem; }

.user-bubble {
    background: #1e1e1e;
    border: 1px solid #2a2a2a;
    border-radius: 12px 12px 2px 12px;
    padding: 0.8rem 1rem;
    max-width: 80%;
    margin-left: auto;
    font-size: 0.9rem;
    color: #e8e8e8;
}

.model-bubble {
    background: #161616;
    border: 1px solid #222;
    border-radius: 2px 12px 12px 12px;
    padding: 0.8rem 1rem;
    max-width: 80%;
    margin-right: auto;
    font-size: 0.9rem;
    color: #ccc;
    line-height: 1.7;
}

.sender-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.3rem;
}

.you-label       { color: #555; text-align: right; }
.llama-label     { color: #a855f7; }
.gpt4o-label     { color: #22c55e; }
.gpt4omini-label { color: #3b82f6; }

.stTextArea textarea {
    background-color: #161616 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 8px !important;
    color: #e8e8e8 !important;
    font-family: 'Sora', sans-serif !important;
    font-size: 0.9rem !important;
}

.stButton > button {
    background: #1a1a1a !important;
    color: #ccc !important;
    font-family: 'Sora', sans-serif !important;
    font-weight: 500 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}

.stButton > button:hover {
    border-color: #444 !important;
    color: #fff !important;
}

.picker-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: #444;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.5rem;
}

hr { border-color: #1a1a1a !important; }
</style>
""", unsafe_allow_html=True)

# ── GitHub Models client ───────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    return OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=token
    )

# ── Session state ──────────────────────────────────────────────────────────────
if "transcript" not in st.session_state:
    st.session_state.transcript = Transcript()

if "prompt_input" not in st.session_state:
    st.session_state.prompt_input = ""

if "insert_mention" not in st.session_state:
    st.session_state.insert_mention = ""

# Apply any pending mention insertion before rendering input
if st.session_state.insert_mention:
    current = st.session_state.get("prompt_input", "")
    st.session_state.prompt_input = current + st.session_state.insert_mention + " "
    st.session_state.insert_mention = ""

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='font-family: Sora, sans-serif; font-weight: 700;
            font-size: 1.5rem; color: #fff; margin-bottom: 0.2rem;'>
    ⬡ ai-roundtable
</div>
<div style='font-family: JetBrains Mono, monospace; font-size: 0.65rem;
            color: #333; margin-bottom: 1.5rem; letter-spacing: 0.1em;'>
    A GROUP CHAT WHERE YOUR CONTACTS ARE AI MODELS
</div>
""", unsafe_allow_html=True)

# ── Token check ────────────────────────────────────────────────────────────────
client = get_client()
if not client:
    st.error("GITHUB_TOKEN not found. Run: export GITHUB_TOKEN=your_token_here")
    st.stop()

# ── Render transcript ──────────────────────────────────────────────────────────
def get_css_class(sender: str) -> str:
    return sender.lower().replace("-", "").replace(" ", "") + "-label"

def render_transcript():
    for msg in st.session_state.transcript.messages:
        if msg["role"] == "user":
            st.markdown(f"""
            <div class='chat-row'>
                <div class='sender-label you-label'>You · {msg['timestamp']}</div>
                <div class='user-bubble'>{msg['content']}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            sender = msg["sender"]
            css_class = get_css_class(sender)
            emoji = next(
                (v["emoji"] for v in AVAILABLE_MODELS.values()
                 if v["name"] == sender), "⬡"
            )
            st.markdown(f"""
            <div class='chat-row'>
                <div class='sender-label {css_class}'>
                    {emoji} {sender} · {msg['timestamp']}
                </div>
                <div class='model-bubble'>{msg['content']}</div>
            </div>
            """, unsafe_allow_html=True)

render_transcript()

# ── Query model ────────────────────────────────────────────────────────────────
def query_model(model_config: dict, prompt: str) -> str:
    all_model_names = [v["name"] for v in AVAILABLE_MODELS.values()]
    system = get_system_prompt(
        model_config["name"],
        all_model_names,
        model_config["strength"]
    )

    history = st.session_state.transcript.get_history_for_model(
        model_config["name"]
    )

    messages = [{"role": "system", "content": system}] + history

    try:
        response = client.chat.completions.create(
            model=model_config["model_id"],
            messages=messages,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠ Error: {str(e)}"

# ── Input section ──────────────────────────────────────────────────────────────
st.markdown("---")

# Model picker buttons
st.markdown("<div class='picker-label'>Add to prompt</div>", unsafe_allow_html=True)

picker_cols = st.columns(len(AVAILABLE_MODELS))

for col, (mention, config) in zip(picker_cols, AVAILABLE_MODELS.items()):
    with col:
        if st.button(
            f"{config['emoji']} {mention}",
            use_container_width=True,
            key=f"pick_{mention}"
        ):
            st.session_state.insert_mention = mention
            st.rerun()

# Prompt text area
prompt_value = st.text_area(
    "Your message",
    value=st.session_state.prompt_input,
    placeholder="click a model above or type @llama, @gpt4o, @gpt4omini",
    height=80,
    label_visibility="collapsed"
)

# Send and clear buttons
col1, col2 = st.columns([1, 5])

with col1:
    send = st.button("Send →", use_container_width=True)

with col2:
    if st.button("Clear roundtable", use_container_width=False):
        st.session_state.transcript = Transcript()
        st.session_state.prompt_input = ""
        st.rerun()

# ── Send message ───────────────────────────────────────────────────────────────
if send and prompt_value.strip():
    prompt = prompt_value.strip()
    st.session_state.transcript.add_user_message(prompt)
    mentioned = parse_mentions(prompt)

    if not mentioned:
        st.warning("No one was mentioned. Click a model button above.")
        st.session_state.transcript.messages.pop()
    else:
        with st.spinner(""):
            for model_config in mentioned:
                response = query_model(model_config, prompt)
                st.session_state.transcript.add_model_message(
                    model_config["name"],
                    response
                )

    # Clear prompt after send
    st.session_state.prompt_input = ""
    st.rerun()