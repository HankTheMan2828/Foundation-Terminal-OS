"""Client for the on-device AI assistant (spec §5) — SEPARATE from Frank.

The assistant talks to the SAME local model server Frank's sensor uses
(bitnet.cpp / llama.cpp's `llama-server`, an OpenAI-compatible endpoint on
127.0.0.1:8080 — see frank-ai.service / docs/FRANK-LOCAL-AI.md). Sharing one
inference server means one model on the box, not two copies eating RAM.

"Same model, separate trust domain": this client is an ordinary chat client. It
has NO access to Frank's data, verdicts, config, or enforcement — it only POSTs
chat turns to the model endpoint and reads the reply, exactly as any local app
would. Frank's isolation is untouched; the operator gains no power over Frank by
chatting with the model (the assistant can't even see Frank's socket).

Local only (operator decision): no cloud provider, no API key, no network
fallback. If frank-ai.service is not up (model/binary not staged), calls return
None and the screen shows a clear offline notice instead of phoning home.

Config (all optional, technician overrides — still loopback/local endpoints):
  env  FOUNDATIONHUB_AI_URL / FOUNDATIONHUB_AI_MODEL
  file /etc/foundationhub/aichat.env  (same keys; assistant's own file, never
       Frank's secrets).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Local inference server (loopback, same one frank-ai.service serves).
DEFAULT_LOCAL_URL = "http://127.0.0.1:8080/v1/chat/completions"
DEFAULT_LOCAL_MODEL = "bitnet-b1.58-2B-4T"

URL_ENV = "FOUNDATIONHUB_AI_URL"
MODEL_ENV = "FOUNDATIONHUB_AI_MODEL"
KEY_FILE = Path(os.environ.get(
    "FOUNDATIONHUB_AICHAT_ENV", "/etc/foundationhub/aichat.env"))

SYSTEM_PROMPT = (
    "You are the on-device assistant for Foundation TerminalOS, a minimal "
    "terminal operating system. You run locally on the user's machine. Be "
    "concise, direct, and helpful. You are a general assistant and are NOT the "
    "overseer (Frank); you have no role in monitoring or restricting the user."
)

# Keep replies bounded on a small local model, and don't wedge the Hub UI if the
# server hangs. BitNet on a mini-PC CPU can be slow on the first tokens after a
# cold start — 30s was too tight and looked like "offline" during generation.
_MAX_TOKENS = 512
_TIMEOUT_S = 120
_PROBE_TIMEOUT_S = 3


def _parse_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines from the assistant's env file. Never raises."""
    out: dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _load_settings() -> tuple[str, str]:
    """Resolve (url, model) from env vars + aichat.env.

    Precedence: process env wins over the file, so a technician can override
    a baked-in aichat.env without editing it. No API keys — local only.
    """
    file_vals = _parse_env_file(KEY_FILE)
    url = (os.environ.get(URL_ENV)
           or file_vals.get(URL_ENV)
           or DEFAULT_LOCAL_URL)
    model = (os.environ.get(MODEL_ENV)
             or file_vals.get(MODEL_ENV)
             or DEFAULT_LOCAL_MODEL)
    return url, model


@dataclass
class ChatResult:
    """Outcome of one chat turn. `text` is set on success; otherwise `error`
    is a short, operator-facing reason (never a stack trace)."""
    text: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.text)


def _message_content(choice: dict) -> str | None:
    """Pull assistant text from an OpenAI-compatible choice.

    Handles the classic string `content` and the newer content-parts list
    some servers return. Returns None if empty/unusable.
    """
    try:
        msg = choice["message"]
        content = msg.get("content")
    except (KeyError, TypeError, AttributeError):
        return None
    if content is None:
        return None
    if isinstance(content, str):
        text = content.strip()
        return text or None
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                # OpenAI content-part shape: {"type":"text","text":"..."}
                t = part.get("text")
                if isinstance(t, str):
                    parts.append(t)
        text = "".join(parts).strip()
        return text or None
    return None


class AssistantClient:
    """Minimal chat client for the local model endpoint. Never raises."""

    def __init__(self, url: str | None = None, model: str | None = None,
                 api_key: str | None = None):
        # api_key is accepted for older call sites but never used (local-only).
        _ = api_key
        file_url, file_model = _load_settings()
        self.url = url if url is not None else file_url
        self.model = model if model is not None else file_model
        # Last failure reason, for the screen to surface (cleared on success).
        self.last_error: str | None = None

    def reachable(self) -> bool:
        """Cheap probe: is the local model server answering?

        Prefers llama-server's `/health` endpoint (derived from the chat URL).
        Falls back to GET on the chat path (405/404 still count as "up").
        Only connection failures count as offline. Never raises.
        """
        candidates = []
        # http://127.0.0.1:8080/v1/chat/completions → http://127.0.0.1:8080/health
        base = self.url
        if "/v1/chat/completions" in base:
            candidates.append(base.replace("/v1/chat/completions", "/health"))
        elif base.rstrip("/").endswith("/v1"):
            candidates.append(base.rstrip("/") + "/health")
        candidates.append(self.url)
        for url in candidates:
            try:
                req = urllib.request.Request(
                    url, method="GET",
                    headers={"Accept": "application/json"})
                try:
                    urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT_S)
                except urllib.error.HTTPError:
                    return True
                return True
            except (urllib.error.URLError, OSError, ValueError):
                continue
        return False

    def chat(self, history: list[dict]) -> str | None:
        """Send the conversation and return the assistant reply, or None.

        `history` is the running turn list; the system prompt is prepended here
        so callers only track the visible user/assistant exchange.
        """
        result = self.complete(history)
        self.last_error = result.error
        return result.text

    def complete(self, history: list[dict]) -> ChatResult:
        """Like chat(), but returns a ChatResult with an explicit error code.

        Local only: one POST to the configured (default loopback) endpoint.
        No cloud fallback — if frank-ai.service is down, the operator stages
        the binary + GGUF (docs/FRANK-LOCAL-AI.md).
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        result = self._post(self.url, self.model, messages)
        if result.ok:
            self.last_error = None
        else:
            self.last_error = result.error
        return result

    def _post(self, url: str, model: str, messages: list[dict]) -> ChatResult:
        payload = json.dumps({
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "temperature": 0.7,
            "messages": messages,
        }).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=payload, headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                raw = resp.read().decode()
            data = json.loads(raw)
        except urllib.error.HTTPError:
            # Server answered but rejected the request (wrong model name, bad
            # payload). Surface as http so the UI can distinguish it from a
            # dead frank-ai.service.
            return ChatResult(error="http")
        except (urllib.error.URLError, TimeoutError, OSError):
            return ChatResult(error="offline")
        except (ValueError, json.JSONDecodeError):
            return ChatResult(error="bad_response")

        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError):
            return ChatResult(error="bad_response")
        text = _message_content(choice if isinstance(choice, dict) else {})
        if not text:
            return ChatResult(error="empty")
        return ChatResult(text=text)
