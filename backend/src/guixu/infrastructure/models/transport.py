from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import urlparse

import httpx


class ModelTransportError(RuntimeError):
    def __init__(self, code: str, *, status: int | None = None, retryable: bool = False, attempts: int = 1) -> None:
        super().__init__(code); self.code = code; self.status = status; self.retryable = retryable; self.attempts = attempts


@dataclass(frozen=True)
class ModelResponse:
    content: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    request_hash: str
    attempts: int


def validate_endpoint(base_url: str, trust_scope: str, provider: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ModelTransportError("MODEL_URL_INVALID")
    host = parsed.hostname.lower().strip("[]")
    loopback = host in {"127.0.0.1", "::1", "localhost"}
    if provider == "deepseek" and (parsed.scheme != "https" or host != "api.deepseek.com" or trust_scope != "cloud"):
        raise ModelTransportError("DEEPSEEK_ENDPOINT_NOT_ALLOWED")
    if trust_scope == "loopback" and not loopback:
        raise ModelTransportError("LOOPBACK_REQUIRED")
    if trust_scope == "trusted_lan" and loopback:
        raise ModelTransportError("TRUST_SCOPE_MISMATCH")
    if trust_scope == "trusted_lan":
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or 80, type=socket.SOCK_STREAM)}
        except (OSError, ValueError) as exc:
            raise ModelTransportError("LAN_HOST_UNRESOLVED") from exc
        if not addresses or any(not (address.is_private or address.is_link_local) for address in addresses):
            raise ModelTransportError("TRUSTED_LAN_REQUIRED")
    return base_url.rstrip("/")


class OpenAICompatibleTransport:
    def __init__(self, *, client_factory: Callable[..., httpx.Client] = httpx.Client,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self.client_factory = client_factory; self.sleeper = sleeper

    def chat(self, *, base_url: str, model_id: str, messages: list[dict[str, Any]], secret: str | None,
             timeout_seconds: int, extra: dict[str, Any] | None = None, max_attempts: int = 3) -> ModelResponse:
        body = {"model": model_id, "messages": messages, "stream": False, **(extra or {})}
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        request_hash = hashlib.sha256(encoded).hexdigest()
        headers = {"Content-Type": "application/json"}
        if secret: headers["Authorization"] = f"Bearer {secret}"
        started = time.perf_counter()
        with self.client_factory(timeout=timeout_seconds, follow_redirects=False, trust_env=False) as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    response = client.post(base_url.rstrip("/") + "/chat/completions", headers=headers, content=encoded)
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt == max_attempts: raise ModelTransportError("MODEL_NETWORK_ERROR", retryable=True, attempts=attempt) from exc
                    continue
                if response.status_code in {401, 403}:
                    raise ModelTransportError("MODEL_AUTH_FAILED", status=response.status_code, attempts=attempt)
                if response.is_redirect:
                    raise ModelTransportError("MODEL_REDIRECT_BLOCKED", status=response.status_code, attempts=attempt)
                if response.status_code == 429:
                    if attempt == max_attempts: raise ModelTransportError("MODEL_RATE_LIMITED", status=429, retryable=True, attempts=attempt)
                    delay = self._retry_after(response.headers.get("Retry-After")); self.sleeper(min(delay, 30.0)); continue
                if response.status_code >= 500:
                    if attempt == max_attempts: raise ModelTransportError("MODEL_SERVER_ERROR", status=response.status_code, retryable=True, attempts=attempt)
                    continue
                if response.status_code >= 400:
                    raise ModelTransportError("MODEL_REQUEST_REJECTED", status=response.status_code, attempts=attempt)
                try:
                    payload = response.json(); content = payload["choices"][0]["message"]["content"]
                    usage = payload.get("usage") or {}
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise ModelTransportError("MODEL_RESPONSE_INVALID", attempts=attempt) from exc
                return ModelResponse(str(content), usage.get("prompt_tokens"), usage.get("completion_tokens"),
                                     int((time.perf_counter()-started)*1000), request_hash, attempt)
        raise AssertionError("unreachable")

    @staticmethod
    def _retry_after(value: str | None) -> float:
        if not value: return 1.0
        try: return max(0.0, float(value))
        except ValueError:
            try: return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
            except (TypeError, ValueError): return 1.0


class DeepSeekAdapter:
    def __init__(self, transport: OpenAICompatibleTransport) -> None: self.transport = transport
    def chat(self, profile: dict[str, Any], messages: list[dict[str, Any]], secret: str | None, *, json_mode: bool = False, max_attempts: int = 3) -> ModelResponse:
        validate_endpoint(profile["base_url"], profile.get("trust_scope", "cloud"), "deepseek")
        extra: dict[str, Any] = {}
        mode = profile["options"].get("thinking_mode", "disabled")
        if mode != "server_default": extra["thinking"] = {"type": mode}
        if json_mode: extra["response_format"] = {"type": "json_object"}
        return self.transport.chat(base_url=profile["base_url"], model_id=profile["model_id"], messages=messages,
                                   secret=secret, timeout_seconds=profile["options"].get("timeout_seconds", 60), extra=extra, max_attempts=max_attempts)


class QwenLocalAdapter:
    def __init__(self, transport: OpenAICompatibleTransport) -> None: self.transport = transport
    def chat(self, profile: dict[str, Any], messages: list[dict[str, Any]], secret: str | None, *, json_mode: bool = False, max_attempts: int = 3) -> ModelResponse:
        validate_endpoint(profile["base_url"], profile.get("trust_scope", "loopback"), "qwen_local")
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        return self.transport.chat(base_url=profile["base_url"], model_id=profile["model_id"], messages=messages,
                                   secret=secret, timeout_seconds=profile["options"].get("timeout_seconds", 120), extra=extra, max_attempts=max_attempts)
