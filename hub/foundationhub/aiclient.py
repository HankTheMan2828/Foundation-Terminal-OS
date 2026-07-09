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
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# The local inference server (loopback, same one frank-ai.service serves).
# Overridable so a technician can point the assistant at a different local model
# or an OpenAI-compatible endpoint without a code change.
DEFAULT_URL = os.environ.get(
    "FOUNDATIONHUB_AI_URL", "http://127.0.0.1:8080/v1/chat/completions")
DEFAULT_MODEL = os.environ.get("FOUNDATIONHUB_AI_MODEL", "bitnet-b1.58-2B-4T")

# Optional bearer key. A local llama-server needs none; a key is only used if the
# operator pointed the URL at an endpoint that wants one. Kept in the assistant's
# OWN file (never Frank's) so the two credential surfaces stay separate (§5).
KEY_ENV = "MISTRAL_API_KEY"
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


def _load_key() -> str | None:
    if os.environ.get(KEY_ENV):
        return os.environ[KEY_ENV]
    try:
        for line in KEY_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{KEY_ENV}="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


class AssistantClient:
    """Minimal chat client for the local model endpoint. Never raises."""

    def __init__(self, url: str = DEFAULT_URL, model: str = DEFAULT_MODEL):
        self.url = url
        self.model = model
        self.api_key = _load_key()

    def chat(self, history: list[dict]) -> str | None:
        """Send the conversation (list of {"role","content"}) and return the
        assistant's reply text, or None if the model isn't reachable.

        `history` is the running turn list; we prepend the system prompt here so
        callers only track the visible user/assistant exchange.
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        payload = json.dumps({
            "model": self.model,
            "max_tokens": _MAX_TOKENS,
            "temperature": 0.7,
            "messages": messages,
        }).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
            # Server down / not installed / malformed reply: treat as offline.
            return None
