# app/transcript.py
# Shared conversation transcript for ai-roundtable
# Every message — yours and all models — lives here

from datetime import datetime
from typing import List, Dict

class Transcript:
    def __init__(self):
        self.messages: List[Dict] = []

    def add_user_message(self, content: str):
        """Add your message to the transcript"""
        self.messages.append({
            "role": "user",
            "sender": "You",
            "content": content,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    def add_model_message(self, sender: str, content: str):
        """Add a model response to the transcript"""
        self.messages.append({
            "role": "assistant",
            "sender": sender,
            "content": content,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    def get_history_for_model(self, model_name: str) -> List[Dict]:
        """
        Return full transcript formatted for API call.
        Every model gets everything — full context always.
        """
        history = []

        for msg in self.messages:
            if msg["role"] == "user":
                history.append({
                    "role": "user",
                    "content": msg["content"]
                })
            else:
                # Label who said what so models know the source
                history.append({
                    "role": "assistant",
                    "content": f"{msg['sender']}: {msg['content']}"
                })

        return history

    def is_empty(self) -> bool:
        return len(self.messages) == 0