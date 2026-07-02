"""The player screen: library / queue list on top, now-playing block below.

One curses window, two views toggled with TAB. Frugal redraw: the input
loop blocks when stopped and ticks at 500 ms only while a track is loaded
(the progress bar is the only thing that moves without a keypress) — same
budget philosophy as the Hub's system monitor.
"""
from __future__ import annotations

import curses

from . import chrome, decoders, labels, library, pcm
from .player import Player, PLAYING, PAUSED
from .playlist import Playlist

KEYS_UP = {curses.KEY_UP, ord("k")}
KEYS_DOWN = {curses.KEY_DOWN, ord("j")}
KEYS_SELECT = {curses.KEY_ENTER, ord("\n"), ord("\r")}
KEYS_QUIT = {27, ord("q"), ord("Q")}

_TICK_MS = 500


class MediaTUI:
    def __init__(self, media_root):
        self.root = media_root
        self.engine = decoders.engine_available()
        self.tracks: list[library.Track] = library.scan(media_root)
        self.playlist = Playlist()
        self.player = Player(self.playlist)
        self.view = labels.VIEW_LIBRARY
        self.sel = {labels.VIEW_LIBRARY: 0, labels.VIEW_QUEUE: 0}
        self.top = {labels.VIEW_LIBRARY: 0, labels.VIEW_QUEUE: 0}
        self.msg = ""            # transient status, cleared on next key

    # ── state helpers ─────────────────────────────────────────────────────

    def _rows(self) -> list[library.Track]:
        if self.view == labels.VIEW_LIBRARY:
            return self.tracks
        return self.playlist.tracks

    def _clamp(self) -> None:
        n = len(self._rows())
        self.sel[self.view] = max(0, min(self.sel[self.view], n - 1)) if n else 0

    def _toggle_view(self) -> None:
        if self.view == labels.VIEW_LIBRARY:
            self.view = labels.VIEW_QUEUE
        else:
            self.view = labels.VIEW_LIBRARY
            self.tracks = library.scan(self.root)   # cheap; only on re-entry
        self._clamp()

    # ── input ─────────────────────────────────────────────────────────────

    def handle_key(self, key: int) -> bool:
        """Returns False to quit."""
        self.msg = ""
        rows = self._rows()
        i = self.sel[self.view]
        if key in KEYS_QUIT:
            return False
        if key in KEYS_UP and rows:
            self.sel[self.view] = (i - 1) % len(rows)
        elif key in KEYS_DOWN and rows:
            self.sel[self.view] = (i + 1) % len(rows)
        elif key == ord("\t"):
            self._toggle_view()
        elif key in KEYS_SELECT and rows:
            self._select(rows[i])
        elif key in (ord("a"), ord("A")) and self.view == labels.VIEW_LIBRARY and rows:
            track = rows[i]
            if track.needs_engine and not self.engine:
                self.msg = labels.NEEDS_ENGINE
            else:
                self.playlist.add(track)
                self.msg = f"{labels.QUEUED}: {track.name}"
        elif key in (ord("x"), ord("X")) and self.view == labels.VIEW_QUEUE and rows:
            self.playlist.remove(i)
            self._clamp()
        elif key in (ord("c"), ord("C")) and self.view == labels.VIEW_QUEUE:
            self.player.stop()
            self.playlist.clear()
            self._clamp()
        elif key == ord(" "):
            self.player.toggle_pause()
        elif key in (ord("s"), ord("S")):
            self.player.stop()
        elif key in (ord("n"), ord("N")):
            self.player.next()
        elif key in (ord("b"), ord("B")):
            self.player.prev()
        elif key == curses.KEY_LEFT:
            self.player.seek(-5)
        elif key == curses.KEY_RIGHT:
            self.player.seek(+5)
        elif key in (ord("+"), ord("=")):
            self.msg = f"{labels.VOLUME} {self.player.adjust_volume(+5)}%"
        elif key in (ord("-"), ord("_")):
            self.msg = f"{labels.VOLUME} {self.player.adjust_volume(-5)}%"
        elif key in (ord("r"), ord("R")):
            self.playlist.repeat = not self.playlist.repeat
        return True

    def _select(self, track: library.Track) -> None:
        if track.needs_engine and not self.engine:
            self.msg = labels.NEEDS_ENGINE
            return
        if self.view == labels.VIEW_LIBRARY:
            self.playlist.play_now(track)
        else:
            self.playlist.jump(self.sel[self.view])
        self.player.play_current()

    # ── drawing ───────────────────────────────────────────────────────────

    def draw(self, win) -> None:
        top, left = chrome.draw_chrome(win, labels.MEDIA_TITLE, labels.MEDIA_TAGLINE)
        h, w = win.getmaxyx()
        width = max(10, w - 2 * left)
        list_h = max(1, h - top - 7)   # leave room for the now-playing block

        self._draw_header(win, top, left, width)
        self._draw_list(win, top + 2, left, width, list_h)
        self._draw_nowplaying(win, h - 6, left, width)

        if self.player.error:
            chrome.draw_statusbar(win, self.player.error, warn=True)
        elif self.msg:
            chrome.draw_statusbar(win, self.msg)
        elif self.view == labels.VIEW_QUEUE:
            chrome.draw_statusbar(win, labels.HINT_QUEUE)
        else:
            chrome.draw_statusbar(win, labels.HINT_LIBRARY)
        win.noutrefresh()
        curses.doupdate()

    def _draw_header(self, win, y, left, width) -> None:
        rows = self._rows()
        head = f"{self.view} · {len(rows)}"
        if self.playlist.repeat:
            head += f" · {labels.REPEAT_ON}"
        try:
            win.addstr(y, left, head[:width], chrome.attr(chrome.PAIR_ACCENT, bold=True))
        except curses.error:
            pass

    def _draw_list(self, win, y0, left, width, list_h) -> None:
        rows = self._rows()
        if not rows:
            empty = (labels.EMPTY_LIBRARY if self.view == labels.VIEW_LIBRARY
                     else labels.EMPTY_QUEUE)
            try:
                win.addstr(y0, left, empty[:width], chrome.attr(chrome.PAIR_DIM, dim=True))
            except curses.error:
                pass
            return
        sel = self.sel[self.view]
        top = self.top[self.view]
        if sel < top:
            top = sel
        elif sel >= top + list_h:
            top = sel - list_h + 1
        self.top[self.view] = top

        queue_now = (self.playlist.index
                     if self.view == labels.VIEW_QUEUE else -1)
        for row, track in enumerate(rows[top: top + list_h], start=top):
            y = y0 + row - top
            selected = row == sel
            disabled = track.needs_engine and not self.engine
            if disabled:
                a = chrome.attr(chrome.PAIR_DIM, dim=True)
            elif selected:
                a = chrome.attr(chrome.PAIR_HILITE, bold=True)
            else:
                a = chrome.attr(chrome.PAIR_NORMAL)
            marker = "▶ " if selected else "  "
            now = "♪ " if row == queue_now else "  "
            line = f"{marker}{now}{track.name}"
            try:
                win.addstr(y, left, line[:width].ljust(width), a)
            except curses.error:
                pass

    def _draw_nowplaying(self, win, y, left, width) -> None:
        p = self.player
        state = {PLAYING: labels.STATE_PLAYING,
                 PAUSED: labels.STATE_PAUSED}.get(p.state, labels.STATE_STOPPED)
        name = p.track.name if p.track is not None else "—"
        line1 = f"{labels.NOW_PLAYING} [{state}] {name}"
        pos, dur = p.position, p.duration or 0.0
        clock = f"{pcm.fmt_time(pos)} / {pcm.fmt_time(dur) if dur else '--:--'}"
        vol = f"{labels.VOLUME} {p.volume}%"
        bar_w = max(4, width - len(clock) - len(vol) - 6)
        line2 = f"[{pcm.progress_bar(pos, dur, bar_w)}] {clock}  {vol}"
        try:
            win.hline(y, 1, curses.ACS_HLINE, max(1, win.getmaxyx()[1] - 2))
            win.addstr(y + 1, left, line1[:width],
                       chrome.attr(chrome.PAIR_ACCENT, bold=p.state == PLAYING))
            win.addstr(y + 2, left, line2[:width], chrome.attr(chrome.PAIR_NORMAL))
            win.addstr(y + 3, left, labels.HINT_SEEK[:width],
                       chrome.attr(chrome.PAIR_DIM, dim=True))
        except curses.error:
            pass

    # ── main loop ─────────────────────────────────────────────────────────

    def run(self, stdscr) -> None:
        chrome.init(stdscr)
        curses.curs_set(0)
        stdscr.keypad(True)
        try:
            while True:
                # Tick while a track is loaded (progress bar moves); block
                # on input otherwise — no busy loop when idle.
                stdscr.timeout(_TICK_MS if self.player.track is not None else -1)
                self.draw(stdscr)
                key = stdscr.getch()
                if key == -1:
                    continue        # tick: just redraw
                if not self.handle_key(key):
                    return
        finally:
            self.player.close()
