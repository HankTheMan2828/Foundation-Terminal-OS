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

Dependency-free on purpose: uses stdlib urllib, so the Hub needs no `requests`.
Everything degrades gracefully off-device — if the server isn't up (dev box, or
an install that didn't stage the model), calls return None and the screen shows
a clear offline notice instead of crashing.

Config (all optional, technician overrides):
  env  FOUNDATIONHUB_AI_URL / FOUNDATIONHUB_AI_MODEL / MISTRAL_API_KEY
  file /etc/foundationhub/aichat.env  (same keys; assistant's own file, never
       Frank's secrets). If a key is present and the local server is down, the
       client falls back to Mistral's cloud endpoint so a key still does what
       INSTALL.md §2 promises.
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
# Cloud fallback used only when a key is configured and local is unreachable.
CLOUD_URL = "https://api.mistral.ai/v1/chat/completions"
CLOUD_MODEL = "mistral-small-latest"

KEY_ENV = "MISTRAL_API_KEY"
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

# Keep replies snappy on a small local model, and don't wedge the Hub UI if the
# server hangs: a bounded timeout means the worst case is a "not reachable" line.
_MAX_TOKENS = 512
_TIMEOUT_S = 30
_PROBE_TIMEOUT_S = 2


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


def _load_settings() -> tuple[str, str, str | None]:
    """Resolve (url, model, api_key) from env vars + aichat.env.

    Precedence: process env wins over the file, so a technician can override
    a baked-in aichat.env without editing it.
    """
    file_vals = _parse_env_file(KEY_FILE)
    url = (os.environ.get(URL_ENV)
           or file_vals.get(URL_ENV)
           or DEFAULT_LOCAL_URL)
    model = (os.environ.get(MODEL_ENV)
             or file_vals.get(MODEL_ENV)
             or DEFAULT_LOCAL_MODEL)
    key = (os.environ.get(KEY_ENV)
           or file_vals.get(KEY_ENV)
           or None)
    return url, model, key


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
        file_url, file_model, file_key = _load_settings()
        self.url = url if url is not None else file_url
        self.model = model if model is not None else file_model
        self.api_key = api_key if api_key is not None else file_key
        # Last failure reason, for the screen to surface (cleared on success).
        self.last_error: str | None = None

    def reachable(self) -> bool:
        """Cheap probe: can we open a TCP connection to the configured host?

        Not a full chat call — just enough for the intro line to say whether
        the model server looks up. Never raises.
        """
        try:
            req = urllib.request.Request(
                self.url, method="GET",
                headers={"Accept": "application/json"})
            # GET on /v1/chat/completions often 405/404 — that still means the
            # server is up. Only connection failures count as offline.
            try:
                urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT_S)
            except urllib.error.HTTPError:
                return True
            return True
        except (urllib.error.URLError, OSError, ValueError):
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
        """Like chat(), but returns a ChatResult with an explicit error code."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        result = self._post(self.url, self.model, messages, auth=bool(self.api_key))
        if result.ok:
            self.last_error = None
            return result

        # Local down + operator put a Mistral key in aichat.env: honour the
        # INSTALL.md §2 cloud path so a key still makes the assistant useful
        # when frank-ai.service isn't staged (dev box, offline install, etc.).
        # Only fall back when the primary URL is still the local default —
        # if the technician pointed the URL elsewhere, do not second-guess them.
        using_local = self.url.rstrip("/") == DEFAULT_LOCAL_URL.rstrip("/")
        if (using_local and self.api_key
                and result.error in ("offline", "http", "empty", "bad_response")):
            cloud = self._post(CLOUD_URL, CLOUD_MODEL, messages, auth=True)
            if cloud.ok:
                self.last_error = None
                return cloud
            result = cloud

        self.last_error = result.error
        return result

    def _post(self, url: str, model: str, messages: list[dict], *,
              auth: bool) -> ChatResult:
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
        if auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=payload, headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                raw = resp.read().decode()
            data = json.loads(raw)
        except urllib.error.HTTPError:
            # Server answered but rejected the request (wrong model name, bad
            # payload, auth). Surface as http so the UI can distinguish it
            # from a dead frank-ai.service.
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
