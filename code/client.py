from __future__ import annotations

import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import requests

from .config import NIM_BASE_URL_DEFAULT, DEFAULT_TIMEOUT, DEFAULT_MAX_TOKENS

class NimChatClient:
    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: str = NIM_BASE_URL_DEFAULT,
        timeout: int = DEFAULT_TIMEOUT,
        temperature: float = 0.0,
        top_p: float = 0.9,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        retries: int = 1,
        connect_timeout: int = 10,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.retries = retries
        self.connect_timeout = connect_timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    def chat(self, messages: Sequence[Dict[str, str]], response_format: Optional[Dict[str, str]] = None) -> str:
        payload = {
            "model": self.model_name,
            "messages": list(messages),
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        url = f"{self.base_url}/chat/completions"
        last_error: Optional[Exception] = None

        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    timeout=(self.connect_timeout, self.timeout),
                )
                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:
                    raise RuntimeError(
                        f"NIM API error {response.status_code}: {response.text[:1000]}"
                    ) from exc

                data = response.json()
                try:
                    message = data["choices"][0]["message"]
                    content = message.get("content") or message.get("reasoning_content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                    raise KeyError("message.content")
                except (KeyError, IndexError, TypeError) as exc:
                    raise RuntimeError(
                        f"Unexpected NIM response: {json.dumps(data)[:1000]}"
                    ) from exc
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(
                    f"NIM request failed after {self.retries + 1} attempts: {exc}"
                ) from exc

        raise RuntimeError(f"NIM request failed: {last_error}")
