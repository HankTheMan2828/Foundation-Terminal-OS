"""Foundation Media — the ONE in-house media player (BUILD-QUEUE §4).

Standalone TUI program (hybrid model: media is not a Hub screen), launched
by Programs → MEDIA. Audio v1; video is explicitly out of scope. Hybrid
playback backend, operator-approved: pure-stdlib WAV/AIFF decode + ctypes
ALSA output as the in-house core, ffmpeg as an optional broad-format decode
engine (see docs/OPEN-QUESTIONS.md §10).
"""
