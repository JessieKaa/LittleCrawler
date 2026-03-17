import json
import time
import logging
from typing import List, Dict, Optional
import requests

from llm_processor.config import (
    OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL,
    LLM_TEMPERATURE, LLM_MAX_TOKENS, LLM_TIMEOUT,
    MAX_RETRIES, RETRY_DELAY, PROMPT_FILE
)


class LLMClient:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.api_key = OPENAI_API_KEY
        self.api_base = OPENAI_API_BASE
        self.model = OPENAI_MODEL
        self.system_prompt = self._load_prompt()

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")

    def _load_prompt(self) -> str:
        try:
            with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            self.logger.error(f"Prompt file not found: {PROMPT_FILE}")
            raise

    def filter_notes(self, notes: List[Dict]) -> List[Dict]:
        if not notes:
            return []

        notes_for_llm = self._prepare_notes(notes)
        llm_response = self._call_llm(notes_for_llm)

        if not llm_response:
            return []

        return self._parse_response(llm_response)

    def _prepare_notes(self, notes: List[Dict]) -> List[Dict]:
        prepared = []
        for note in notes:
            prepared.append({
                "id": note.get("note_id"),
                "title": note.get("title", ""),
                "desc": note.get("desc", ""),
                "user_nickname": note.get("nickname", ""),
                "ip_location": note.get("ip_location", ""),
            })
        return prepared

    def _call_llm(self, notes_data: List[Dict]) -> Optional[str]:
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        user_message = f"请分析以下数据：\n\n{json.dumps(notes_data, ensure_ascii=False, indent=2)}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS,
        }

        for attempt in range(MAX_RETRIES):
            try:
                self.logger.info(f"LLM API call attempt {attempt + 1}/{MAX_RETRIES}")
                self.logger.info(f"LLM API call headers: {headers}")
                self.logger.info(f"LLM API call payload: {payload}")
                response = requests.post(url, headers=headers, json=payload, timeout=LLM_TIMEOUT)

                if response.status_code == 200:
                    self.logger.info(f"LLM response: {response.text}")
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    self.logger.info(f"LLM response received: {len(content)} chars")
                    return content
                else:
                    self.logger.error(f"API error: {response.status_code} - {response.text[:200]}")

            except Exception as e:
                self.logger.error(f"API call failed: {e}")

            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

        return None

    def _parse_response(self, response: str) -> List[Dict]:
        try:
            json_str = self._extract_json(response)
            if not json_str:
                self.logger.error("Could not extract JSON from response")
                return []

            results = json.loads(json_str)
            if not isinstance(results, list):
                self.logger.error("Response is not a list")
                return []

            self.logger.info(f"Parsed {len(results)} results from LLM")
            return results

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parse error: {e}")
            return []

    def _extract_json(self, response: str) -> Optional[str]:
        text = response.strip()
        if not text:
            return None

        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()

        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()

        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start_idx = text.find(start_char)
            if start_idx == -1:
                continue
            depth = 0
            for i in range(start_idx, len(text)):
                c = text[i]
                if c == start_char:
                    depth += 1
                elif c == end_char:
                    depth -= 1
                    if depth == 0:
                        return text[start_idx:i + 1]
        return None
