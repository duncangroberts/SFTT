"""Client helper for interacting with a local llama.cpp server."""
from __future__ import annotations

import json
import os
from typing import Iterable, Optional, Sequence

import requests


class LLMClientError(RuntimeError):
    """Raised when the local LLM cannot be reached or returns an error."""


class LLMResponseFormatError(LLMClientError):
    """Raised when the LLM response cannot be parsed."""


class LlamaCppClient:
    """Minimal HTTP client that understands llama.cpp server endpoints."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_style: str = "auto",
        timeout: float = 120.0,
    ) -> None:
        env_base = os.environ.get("LLAMA_SERVER_URL") or os.environ.get("LLM_SERVER_URL")
        self.base_url = (base_url or env_base or "http://127.0.0.1:8080").rstrip("/")
        self.model = model or os.environ.get("LLAMA_MODEL") or os.environ.get("LLM_MODEL") or "local"
        self.api_style = api_style or "auto"
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
        max_tokens: int = 512,
        stop: Optional[Sequence[str]] = None,
    ) -> str:
        errors: list[str] = []
        stop_sequences = list(stop or [])
        if self.api_style in ("auto", "openai"):
            try:
                return self._generate_openai(
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    repeat_penalty=repeat_penalty,
                    max_tokens=max_tokens,
                    stop=stop_sequences,
                )
            except LLMClientError as exc:
                errors.append(str(exc))
                if self.api_style == "openai":
                    raise LLMClientError(
                        f"Failed using OpenAI-compatible endpoint: {str(exc)}"
                    )
        if self.api_style in ("auto", "completion"):
            try:
                return self._generate_completion(
                    prompt,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    repeat_penalty=repeat_penalty,
                    max_tokens=max_tokens,
                    stop=stop_sequences,
                )
            except LLMClientError as exc:
                errors.append(str(exc))
                if self.api_style == "completion":
                    raise LLMClientError(
                        f"Failed using completion endpoint: {str(exc)}"
                    )
        if errors:
            raise LLMClientError(" | ".join(errors))
        raise LLMClientError("Unable to obtain a completion from llama.cpp server.")

    def _generate_openai(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str],
        temperature: float,
        top_p: float,
        top_k: int,
        repeat_penalty: float,
        max_tokens: int,
        stop: Sequence[str],
    ) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repetition_penalty": repeat_penalty,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = list(stop)
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LLMClientError(f"HTTP error calling {url}: {exc}") from exc
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise LLMResponseFormatError(f"Invalid JSON from {url}: {exc}") from exc
        choices = data.get("choices") or []
        if not choices:
            raise LLMResponseFormatError("No choices returned from chat/completions endpoint.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseFormatError("Empty content from chat/completions response.")
        return content.strip()

    def _generate_completion(
        self,
        prompt: str,
        *,
        temperature: float,
        top_p: float,
        top_k: int,
        repeat_penalty: float,
        max_tokens: int,
        stop: Sequence[str],
    ) -> str:
        url = f"{self.base_url}/completion"
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if stop:
            payload["stop"] = list(stop)
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LLMClientError(f"HTTP error calling {url}: {exc}") from exc
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise LLMResponseFormatError(f"Invalid JSON from {url}: {exc}") from exc
        if isinstance(data, dict):
            if isinstance(data.get("content"), str):
                text = data["content"]
            elif isinstance(data.get("completion"), str):
                text = data["completion"]
            elif isinstance(data.get("choices"), list) and data["choices"]:
                choice = data["choices"][0]
                if isinstance(choice, dict):
                    text = choice.get("text") or choice.get("content")
                else:
                    text = str(choice)
            else:
                text = None
        else:
            text = None
        if not isinstance(text, str) or not text.strip():
            raise LLMResponseFormatError("Empty completion content returned from /completion endpoint.")
        return text.strip()


def generate_completion(
    prompt: str,
    *,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    top_p: float = 0.9,
    top_k: int = 40,
    repeat_penalty: float = 1.1,
    max_tokens: int = 512,
    stop: Optional[Iterable[str]] = None,
    client: Optional[LlamaCppClient] = None,
) -> str:
    """Convenience wrapper to fetch a completion using shared defaults."""

    active_client = client or LlamaCppClient()
    return active_client.generate(
        prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repeat_penalty=repeat_penalty,
        max_tokens=max_tokens,
        stop=list(stop or []),
    )