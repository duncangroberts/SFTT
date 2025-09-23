"""Runtime helpers for managing a local llama.cpp server."""
from __future__ import annotations

import contextlib
import os
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional
from urllib.parse import urlparse

import requests

from llm_client import LlamaCppClient


class LlamaServerError(RuntimeError):
    """Raised when the llama.cpp server cannot be managed."""


@dataclass
class _ServerContext:
    manager: "LlamaServerManager"
    logger: Optional[Callable[[str], None]]

    def __enter__(self) -> "LlamaServerManager":
        self.manager._ensure_running(self.logger)
        return self.manager

    def __exit__(self, exc_type, exc, tb) -> None:
        self.manager._maybe_stop(self.logger)


class LlamaServerManager:
    """Start and stop a llama.cpp HTTP server on demand."""

    def __init__(
        self,
        *,
        client: Optional[LlamaCppClient] = None,
        base_url: Optional[str] = None,
        model_path: Optional[Path] = None,
        exe_path: Optional[Path] = None,
        extra_args: Optional[Iterable[str]] = None,
        ready_timeout: float = 60.0,
        poll_interval: float = 0.75,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.client = client or LlamaCppClient()
        raw_base = base_url or self.client.base_url
        parsed = urlparse(raw_base if raw_base.startswith("http") else f"http://{raw_base}")
        self.base_url = f"{parsed.scheme or 'http'}://{parsed.netloc}"
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 8080
        self.ready_timeout = ready_timeout
        self.poll_interval = poll_interval
        self.logger = logger

        self.exe_path = exe_path or self._default_exe_path()
        self.model_path = model_path or self._default_model_path()
        self.extra_args = list(extra_args or self._default_extra_args())

        self._proc: Optional[subprocess.Popen] = None
        self._started_locally = False

    def ensure_running(self, logger: Optional[Callable[[str], None]] = None) -> contextlib.AbstractContextManager:
        return _ServerContext(self, logger)

    # Internal helpers ------------------------------------------------- #

    def _ensure_running(self, logger: Optional[Callable[[str], None]]) -> None:
        if self._is_server_responsive():
            if logger:
                logger("LLM discovery: reusing existing llama.cpp server")
            return
        if logger:
            logger("LLM discovery: starting local llama.cpp server ...")
        self._start_process(logger)
        self._wait_until_ready(logger)

    def _maybe_stop(self, logger: Optional[Callable[[str], None]]) -> None:
        if self._proc is None or not self._started_locally:
            return
        if logger:
            logger("LLM discovery: stopping local llama.cpp server")
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        finally:
            self._proc = None
            self._started_locally = False

    def _is_server_responsive(self) -> bool:
        if not self._can_connect(self.host, self.port):
            return False
        url = f"{self.base_url}/health"
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code < 500:
                return True
        except requests.RequestException:
            pass
        # As a fallback, treat an open socket as success.
        return True

    def _start_process(self, logger: Optional[Callable[[str], None]]) -> None:
        if not self.exe_path or not self.exe_path.exists():
            raise LlamaServerError(f"llama-server executable not found at {self.exe_path}")
        if not self.model_path or not self.model_path.exists():
            raise LlamaServerError(f"LLM model file not found at {self.model_path}")

        cmd = [str(self.exe_path), "--model", str(self.model_path), "--host", self.host, "--port", str(self.port)]
        cmd.extend(self.extra_args)

        if logger:
            logger(f"LLM discovery: executing command: {' '.join(cmd)}")

        creationflags = 0
        startupinfo = None
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        else:
            startupinfo = None
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
        except OSError as exc:
            raise LlamaServerError(f"Failed to launch llama-server: {exc}") from exc
        self._started_locally = True
        if logger:
            logger(f"LLM discovery: launched llama-server pid={self._proc.pid}")

    def _wait_until_ready(self, logger: Optional[Callable[[str], None]]) -> None:
        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline:
            if self.logger:
                self.logger(f"LLM discovery: checking for server at {self.base_url}/health")
            if self._proc and self._proc.poll() is not None:
                stdout, stderr = self._proc.communicate(timeout=0.1)
                raise LlamaServerError(
                    f"llama-server exited early with code {self._proc.returncode}: {stderr.decode().strip()}"
                )
            if self._is_server_responsive():
                if logger:
                    logger("LLM discovery: llama-server ready")
                return
            time.sleep(self.poll_interval)
        raise LlamaServerError("Timed out waiting for llama-server to become ready")

    @staticmethod
    def _can_connect(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except OSError:
            return False

    @staticmethod
    def _default_exe_path() -> Path:
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        return Path("tools") / "llama.cpp" / exe_name

    @staticmethod
    def _default_model_path() -> Path:
        env_override = os.environ.get("LLAMA_MODEL_PATH") or os.environ.get("LLM_MODEL_PATH")
        if env_override:
            return Path(env_override)
        model_dir = Path("models")
        if not model_dir.exists():
            raise LlamaServerError("models directory not found; cannot locate GGUF model")
        
        candidates = [f for f in os.listdir(model_dir) if f.endswith('.gguf')]
        if not candidates:
            raise LlamaServerError(
                "No GGUF model files found in models directory. "
                "Download a model such as TinyLlama-1.1B from "
                "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
            )
        return model_dir / candidates[0]

    @staticmethod
    def _default_extra_args() -> Iterator[str]:
        env_args = os.environ.get("LLAMA_SERVER_ARGS") or os.environ.get("LLM_SERVER_ARGS")
        if env_args:
            for token in shlex.split(env_args):
                yield token
        else:
            yield from ()


def manage_llama_server(
    *,
    client: Optional[LlamaCppClient] = None,
    logger: Optional[Callable[[str], None]] = None,
    auto_start: bool = True,
) -> contextlib.AbstractContextManager:
    """Return a context manager that ensures a llama.cpp server is running."""

    if not auto_start:
        return contextlib.nullcontext()
    manager = LlamaServerManager(client=client)
    return manager.ensure_running(logger)
