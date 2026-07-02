"""System info collectors reading /proc directly, stdlib only (BUILD-QUEUE §3).

Parsing is kept pure and fixture-testable: feed raw /proc text in, get
structured data out. The thin `read_*()` wrappers are the only parts that
touch the filesystem, so tests never need a real /proc, and `monitor.py`
never needs to know the file formats.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROC = Path(os.environ.get("FOUNDATIONHUB_PROC", "/proc"))

_CLK_TCK = 100
try:
    _CLK_TCK = os.sysconf("SC_CLK_TCK")
except (AttributeError, ValueError, OSError):
    pass


def available() -> bool:
    """Whether /proc looks readable on this host (degrade path, spec §3.3)."""
    return (PROC / "stat").exists()


# ── CPU (/proc/stat) ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CpuTimes:
    name: str  # "cpu" (aggregate), "cpu0", "cpu1", ...
    user: int
    nice: int
    system: int
    idle: int
    iowait: int
    irq: int
    softirq: int
    steal: int

    @property
    def total(self) -> int:
        return (self.user + self.nice + self.system + self.idle +
                self.iowait + self.irq + self.softirq + self.steal)

    @property
    def idle_total(self) -> int:
        return self.idle + self.iowait


def parse_stat(text: str) -> list[CpuTimes]:
    """Parse the `cpu`/`cpuN` lines of /proc/stat. First entry is the total."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("cpu"):
            continue
        fields = [int(p) for p in parts[1:]]
        fields += [0] * (8 - len(fields))  # older kernels omit trailing fields
        out.append(CpuTimes(parts[0], *fields[:8]))
    return out


def cpu_percent(prev: CpuTimes, curr: CpuTimes) -> float:
    """% busy between two /proc/stat samples of the same cpu line."""
    dt = curr.total - prev.total
    if dt <= 0:
        return 0.0
    d_idle = curr.idle_total - prev.idle_total
    return max(0.0, min(100.0, 100.0 * (dt - d_idle) / dt))


def read_stat() -> list[CpuTimes]:
    return parse_stat((PROC / "stat").read_text())


# ── memory (/proc/meminfo) ───────────────────────────────────────────────────

def parse_meminfo(text: str) -> dict[str, int]:
    """{key: bytes} — /proc/meminfo values are given in kB."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        tokens = rest.strip().split()
        if not tokens:
            continue
        try:
            out[key.strip()] = int(tokens[0]) * 1024
        except ValueError:
            continue
    return out


def read_meminfo() -> dict[str, int]:
    return parse_meminfo((PROC / "meminfo").read_text())


def mem_summary(meminfo: dict[str, int]) -> tuple[int, int, int]:
    """(total, used, available) in bytes, preferring MemAvailable when present."""
    total = meminfo.get("MemTotal", 0)
    avail = meminfo.get("MemAvailable")
    if avail is None:
        avail = (meminfo.get("MemFree", 0) + meminfo.get("Buffers", 0) +
                 meminfo.get("Cached", 0))
    used = max(0, total - avail)
    return total, used, avail


# ── uptime (/proc/uptime) ────────────────────────────────────────────────────

def parse_uptime(text: str) -> float:
    return float(text.split()[0])


def read_uptime() -> float:
    return parse_uptime((PROC / "uptime").read_text())


# ── load average (/proc/loadavg) ─────────────────────────────────────────────

@dataclass(frozen=True)
class LoadAvg:
    one: float
    five: float
    fifteen: float
    running: int
    total_procs: int


def parse_loadavg(text: str) -> LoadAvg:
    parts = text.split()
    running, total = parts[3].split("/")
    return LoadAvg(float(parts[0]), float(parts[1]), float(parts[2]),
                   int(running), int(total))


def read_loadavg() -> LoadAvg:
    return parse_loadavg((PROC / "loadavg").read_text())


# ── network (/proc/net/dev) ──────────────────────────────────────────────────

def parse_net_dev(text: str) -> dict[str, tuple[int, int]]:
    """{iface: (rx_bytes, tx_bytes)}. Caller decides whether to skip "lo"."""
    out: dict[str, tuple[int, int]] = {}
    for line in text.splitlines()[2:]:  # first two lines are headers
        if ":" not in line:
            continue
        iface, _, rest = line.partition(":")
        fields = rest.split()
        if len(fields) < 9:
            continue
        out[iface.strip()] = (int(fields[0]), int(fields[8]))
    return out


def read_net_dev() -> dict[str, tuple[int, int]]:
    return parse_net_dev((PROC / "net" / "dev").read_text())


def net_rates(prev: dict[str, tuple[int, int]], curr: dict[str, tuple[int, int]],
              dt: float) -> dict[str, tuple[float, float]]:
    """{iface: (rx_bytes_per_sec, tx_bytes_per_sec)}."""
    if dt <= 0:
        return {name: (0.0, 0.0) for name in curr}
    out = {}
    for name, (rx, tx) in curr.items():
        prx, ptx = prev.get(name, (rx, tx))
        out[name] = (max(0.0, (rx - prx) / dt), max(0.0, (tx - ptx) / dt))
    return out


# ── processes (/proc/[pid]/...) ──────────────────────────────────────────────

@dataclass(frozen=True)
class ProcSample:
    pid: int
    name: str
    total_ticks: int  # utime + stime, clock ticks
    rss_bytes: int


def parse_proc_stat_line(text: str) -> tuple[str, int, int]:
    """One /proc/[pid]/stat line -> (comm, utime, stime).

    `comm` is parenthesized and may itself contain spaces/parens (process
    names are attacker/user controlled), so it's located by the outermost
    `(...)` rather than naive whitespace splitting."""
    open_p = text.index("(")
    close_p = text.rindex(")")
    comm = text[open_p + 1:close_p]
    rest = text[close_p + 2:].split()
    # Fields after comm, 1-indexed from `state` (field 3 overall): utime is
    # field 14, stime is field 15 -> offsets 11, 12 in this 0-indexed `rest`.
    utime = int(rest[11])
    stime = int(rest[12])
    return comm, utime, stime


def parse_proc_status_rss(text: str) -> int:
    """VmRSS out of /proc/[pid]/status, in bytes (0 if absent)."""
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            tokens = line.split()
            if len(tokens) >= 2:
                return int(tokens[1]) * 1024
    return 0


def list_pids() -> list[int]:
    try:
        return [int(e.name) for e in PROC.iterdir() if e.name.isdigit()]
    except OSError:
        return []


def read_process_samples() -> dict[int, ProcSample]:
    """Best-effort snapshot. A process can exit mid-read — that's normal, not
    an error, so it's just skipped rather than surfaced."""
    out: dict[int, ProcSample] = {}
    for pid in list_pids():
        try:
            comm, utime, stime = parse_proc_stat_line(
                (PROC / str(pid) / "stat").read_text())
            rss = parse_proc_status_rss((PROC / str(pid) / "status").read_text())
        except (OSError, ValueError, IndexError):
            continue
        out[pid] = ProcSample(pid, comm, utime + stime, rss)
    return out


@dataclass(frozen=True)
class ProcRow:
    pid: int
    name: str
    cpu_percent: float
    rss_bytes: int


def process_rows(prev: dict[int, ProcSample], curr: dict[int, ProcSample],
                  dt: float, n_cpus: int = 1) -> list[ProcRow]:
    """CPU% per process since the previous sample, sorted busiest-first."""
    window_ticks = dt * _CLK_TCK * max(1, n_cpus)
    rows = []
    for pid, sample in curr.items():
        prev_sample = prev.get(pid)
        d_ticks = (sample.total_ticks - prev_sample.total_ticks
                   if prev_sample else 0)
        pct = 0.0
        if window_ticks > 0 and d_ticks > 0:
            pct = max(0.0, min(100.0, 100.0 * d_ticks / window_ticks))
        rows.append(ProcRow(sample.pid, sample.name, pct, sample.rss_bytes))
    rows.sort(key=lambda r: r.cpu_percent, reverse=True)
    return rows


# ── formatting ────────────────────────────────────────────────────────────────

def format_bytes(n: float) -> str:
    """Human-scaled byte count, e.g. "512.0 KB", "1.2 GB"."""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def format_rate(bytes_per_sec: float) -> str:
    return f"{format_bytes(bytes_per_sec)}/s"


def format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


# ── one-shot snapshot (used by monitor.py) ───────────────────────────────────

@dataclass
class Sample:
    """Everything the monitor screen needs from a single /proc pass."""
    timestamp: float
    cpu_times: list[CpuTimes]
    meminfo: dict[str, int]
    uptime: float
    loadavg: LoadAvg
    net_dev: dict[str, tuple[int, int]]
    processes: dict[int, ProcSample]


def take_sample() -> Sample:
    import time
    return Sample(
        timestamp=time.monotonic(),
        cpu_times=read_stat(),
        meminfo=read_meminfo(),
        uptime=read_uptime(),
        loadavg=read_loadavg(),
        net_dev=read_net_dev(),
        processes=read_process_samples(),
    )
