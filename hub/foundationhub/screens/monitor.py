"""System Monitor (spec §5, BUILD-QUEUE §3) — retires btop.

View-only: kill/renice is root/overseer territory, not the operator's (queue
§3.2). Refreshes on a ~2s timer via curses' own window timeout rather than a
sleep loop, so a keypress is still handled immediately in between ticks.

Degrades gracefully off-target (queue §3.3): the dev box (Windows, or any
non-Linux host) has no /proc, so this shows an honest placeholder instead of
crashing, the same posture as `session.py`'s hardware helpers.
"""
from __future__ import annotations

import curses

from .. import labels, sysinfo, theme
from ..app import Screen, POP
from ..ui import KEYS_BACK

REFRESH_MS = 2000
PROC_ROWS_SHOWN = 12


class MonitorScreen(Screen):
    title = labels.MONITOR_TITLE
    subtitle = labels.MONITOR_SUBTITLE

    def __init__(self):
        self._available = sysinfo.available()
        self._prev: sysinfo.Sample | None = None
        self._overall_cpu = 0.0
        self._per_core: list[tuple[str, float]] = []
        self._net: dict[str, tuple[float, float]] = {}
        self._proc_rows: list[sysinfo.ProcRow] = []
        self._win = None

    def status_text(self) -> str:
        return labels.MONITOR_HINT

    def draw(self, win, top: int, left: int) -> None:
        self._win = win
        try:
            win.timeout(REFRESH_MS)
        except curses.error:
            pass
        if not self._available:
            self._draw_unavailable(win, top, left)
            return
        self._sample()
        self._draw_live(win, top, left)

    def handle_key(self, key: int, app) -> object:
        if key == -1:
            return None  # timer tick: draw() already resampled, just redraw
        if key in KEYS_BACK:
            if self._win is not None:
                try:
                    self._win.timeout(-1)  # back to blocking for the rest of the Hub
                except curses.error:
                    pass
            return POP
        return None

    # ── sampling ─────────────────────────────────────────────────────────────

    def _sample(self) -> None:
        curr = sysinfo.take_sample()
        if self._prev is not None:
            dt = curr.timestamp - self._prev.timestamp
            if dt <= 0:
                dt = REFRESH_MS / 1000
            prev_cpus = {c.name: c for c in self._prev.cpu_times}
            curr_cpus = {c.name: c for c in curr.cpu_times}
            if "cpu" in prev_cpus and "cpu" in curr_cpus:
                self._overall_cpu = sysinfo.cpu_percent(prev_cpus["cpu"], curr_cpus["cpu"])
            self._per_core = [
                (name, sysinfo.cpu_percent(prev_cpus[name], c))
                for name, c in curr_cpus.items()
                if name != "cpu" and name in prev_cpus
            ]
            self._net = sysinfo.net_rates(self._prev.net_dev, curr.net_dev, dt)
            n_cpus = max(1, len(self._per_core))
            self._proc_rows = sysinfo.process_rows(
                self._prev.processes, curr.processes, dt, n_cpus)
        self._prev = curr

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw_unavailable(self, win, top: int, left: int) -> None:
        try:
            win.addstr(top + 1, left, labels.MONITOR_NO_PROC,
                       theme.attr(theme.PAIR_WARN, bold=True))
            win.addstr(top + 3, left, labels.MONITOR_NO_PROC_DETAIL,
                       theme.attr(theme.PAIR_DIM, dim=True))
        except curses.error:
            pass

    def _draw_live(self, win, top: int, left: int) -> None:
        h, w = win.getmaxyx()
        width = max(10, w - 2 * left)
        row = top

        def line(text: str, *, dim: bool = False, bold: bool = False) -> None:
            nonlocal row
            try:
                win.addstr(row, left, text[:width],
                           theme.attr(theme.PAIR_NORMAL, bold=bold, dim=dim))
            except curses.error:
                pass
            row += 1

        curr = self._prev  # _sample() already advanced this to the latest
        assert curr is not None

        line(f"{labels.MONITOR_CPU}   {self._overall_cpu:5.1f}%", bold=True)
        if self._per_core:
            cores = "  ".join(f"{name.replace('cpu', 'c')}:{pct:4.0f}%"
                               for name, pct in self._per_core)
            line(f"  {cores}", dim=True)

        total, used, _ = sysinfo.mem_summary(curr.meminfo)
        line(f"{labels.MONITOR_MEM}   {sysinfo.format_bytes(used)} / "
             f"{sysinfo.format_bytes(total)}", bold=True)

        load = curr.loadavg
        line(f"{labels.MONITOR_LOAD}  {load.one:.2f} {load.five:.2f} "
             f"{load.fifteen:.2f}   ({load.running}/{load.total_procs} procs)")
        line(f"{labels.MONITOR_UPTIME}  {sysinfo.format_uptime(curr.uptime)}")

        rx_total = sum(rx for rx, _ in self._net.values())
        tx_total = sum(tx for _, tx in self._net.values())
        line(f"{labels.MONITOR_NET}   rx {sysinfo.format_rate(rx_total)}   "
             f"tx {sysinfo.format_rate(tx_total)}")

        row += 1
        line(labels.MONITOR_PROCESSES, dim=True)
        line(labels.MONITOR_PROC_HEADER, dim=True)
        for proc in self._proc_rows[:PROC_ROWS_SHOWN]:
            if row >= h - 3:
                break
            line(f"{proc.pid:>7}  {proc.name[:20]:<20}{proc.cpu_percent:6.1f}% "
                 f"{sysinfo.format_bytes(proc.rss_bytes):>9}")


def screen():
    return MonitorScreen()
