import json
import os
from typing import Dict


class StateManager:
    def __init__(self, state_file: str):
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self) -> Dict:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"last_note_timestamp": 0, "total_processed": 0}

    def save_state(self):
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def get_last_note_timestamp(self) -> int:
        return self.state.get("last_note_timestamp", 0)

    def update_note_timestamp(self, timestamp: int):
        if timestamp > self.state.get("last_note_timestamp", 0):
            self.state["last_note_timestamp"] = timestamp

    def increment_processed(self, count: int):
        self.state["total_processed"] = self.state.get("total_processed", 0) + count
