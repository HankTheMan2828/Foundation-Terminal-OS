"""Headless tests for the /proc parsers (queue §3) — fixture text in, no real
/proc required."""
from foundationhub import sysinfo
from foundationhub.sysinfo import (CpuTimes, ProcSample, cpu_percent, format_bytes,
                            format_rate, format_uptime, mem_summary,
                            net_rates, parse_loadavg, parse_meminfo,
                            parse_net_dev, parse_proc_stat_line,
                            parse_proc_status_rss, parse_stat, parse_uptime,
                            process_rows)


# ── /proc/stat ────────────────────────────────────────────────────────────────

STAT_TEXT = """\
cpu  100 10 50 800 20 0 5 0 0 0
cpu0 50 5 25 400 10 0 2 0 0 0
cpu1 50 5 25 400 10 0 3 0 0 0
intr 12345 0 0 0
ctxt 98765
btime 1700000000
processes 4321
"""


def test_parse_stat_aggregate_and_cores():
    cpus = parse_stat(STAT_TEXT)
    names = [c.name for c in cpus]
    assert names == ["cpu", "cpu0", "cpu1"]
    assert cpus[0].user == 100 and cpus[0].idle == 800


def test_parse_stat_ignores_non_cpu_lines():
    cpus = parse_stat(STAT_TEXT)
    assert all(c.name.startswith("cpu") for c in cpus)


def test_cpu_percent_busy_between_samples():
    prev = CpuTimes("cpu", user=100, nice=0, system=0, idle=900,
                    iowait=0, irq=0, softirq=0, steal=0)
    curr = CpuTimes("cpu", user=150, nice=0, system=0, idle=950,
                    iowait=0, irq=0, softirq=0, steal=0)
    # +50 user, +50 idle, +100 total -> 50% busy
    assert cpu_percent(prev, curr) == 50.0


def test_cpu_percent_zero_delta_is_zero_not_error():
    same = CpuTimes("cpu", 1, 0, 0, 1, 0, 0, 0, 0)
    assert cpu_percent(same, same) == 0.0


# ── /proc/meminfo ─────────────────────────────────────────────────────────────

MEMINFO_TEXT = """\
MemTotal:        8000000 kB
MemFree:         2000000 kB
MemAvailable:    5000000 kB
Buffers:          100000 kB
Cached:          1500000 kB
SwapTotal:       1000000 kB
SwapFree:        1000000 kB
"""


def test_parse_meminfo_converts_kb_to_bytes():
    info = parse_meminfo(MEMINFO_TEXT)
    assert info["MemTotal"] == 8000000 * 1024
    assert info["MemAvailable"] == 5000000 * 1024


def test_mem_summary_prefers_mem_available():
    info = parse_meminfo(MEMINFO_TEXT)
    total, used, avail = mem_summary(info)
    assert total == 8000000 * 1024
    assert avail == 5000000 * 1024
    assert used == total - avail


def test_mem_summary_falls_back_without_mem_available():
    info = {"MemTotal": 1000, "MemFree": 200, "Buffers": 50, "Cached": 100}
    total, used, avail = mem_summary(info)
    assert avail == 350
    assert used == 650


# ── /proc/uptime ──────────────────────────────────────────────────────────────

def test_parse_uptime():
    assert parse_uptime("12345.67 54321.00\n") == 12345.67


def test_format_uptime_scales():
    assert format_uptime(90) == "1m"
    assert format_uptime(3660) == "1h 01m"
    assert format_uptime(90000) == "1d 01h 00m"


# ── /proc/loadavg ─────────────────────────────────────────────────────────────

def test_parse_loadavg():
    load = parse_loadavg("0.50 0.25 0.10 3/456 7890\n")
    assert (load.one, load.five, load.fifteen) == (0.50, 0.25, 0.10)
    assert load.running == 3
    assert load.total_procs == 456


# ── /proc/net/dev ─────────────────────────────────────────────────────────────

NET_DEV_TEXT = """\
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo:  1000       10    0    0    0     0          0         0  1000       10    0    0    0     0       0          0
  eth0: 50000      100    0    0    0     0          0         0 20000       80    0    0    0     0       0          0
"""


def test_parse_net_dev():
    ifaces = parse_net_dev(NET_DEV_TEXT)
    assert ifaces["lo"] == (1000, 1000)
    assert ifaces["eth0"] == (50000, 20000)


def test_net_rates_computes_per_second_deltas():
    prev = {"eth0": (1000, 500)}
    curr = {"eth0": (3000, 1500)}
    rates = net_rates(prev, curr, dt=2.0)
    assert rates["eth0"] == (1000.0, 500.0)


def test_net_rates_zero_dt_is_safe():
    assert net_rates({}, {"eth0": (1, 1)}, dt=0) == {"eth0": (0.0, 0.0)}


# ── /proc/[pid]/stat and /status ──────────────────────────────────────────────

def test_parse_proc_stat_line_simple_comm():
    text = "123 (bash) S 1 123 123 0 -1 0 0 0 0 0 200 100 0 0 20 0 1 0 0"
    comm, utime, stime = parse_proc_stat_line(text)
    assert comm == "bash"
    assert (utime, stime) == (200, 100)


def test_parse_proc_stat_line_comm_with_spaces_and_parens():
    # Process names can contain spaces or even parens; only the outermost
    # parens delimit the comm field.
    text = "1 (weird (name) proc) R 0 1 1 0 -1 0 0 0 0 0 5 3 0 0 20 0 1 0 0"
    comm, utime, stime = parse_proc_stat_line(text)
    assert comm == "weird (name) proc"
    assert (utime, stime) == (5, 3)


def test_parse_proc_status_rss():
    text = "Name:\tbash\nVmRSS:\t   4096 kB\nVmSize:\t 100000 kB\n"
    assert parse_proc_status_rss(text) == 4096 * 1024


def test_parse_proc_status_rss_missing_is_zero():
    assert parse_proc_status_rss("Name:\tbash\n") == 0


def test_process_rows_sorted_busiest_first():
    prev = {
        1: ProcSample(1, "a", total_ticks=100, rss_bytes=1000),
        2: ProcSample(2, "b", total_ticks=100, rss_bytes=2000),
    }
    curr = {
        1: ProcSample(1, "a", total_ticks=110, rss_bytes=1000),
        2: ProcSample(2, "b", total_ticks=300, rss_bytes=2000),
    }
    rows = process_rows(prev, curr, dt=1.0, n_cpus=1)
    assert [r.pid for r in rows] == [2, 1]
    assert rows[0].cpu_percent > rows[1].cpu_percent


def test_process_rows_new_pid_has_zero_percent():
    curr = {5: ProcSample(5, "new", total_ticks=999, rss_bytes=10)}
    rows = process_rows({}, curr, dt=1.0, n_cpus=1)
    assert rows[0].cpu_percent == 0.0


# ── formatting ────────────────────────────────────────────────────────────────

def test_format_bytes_scales():
    assert format_bytes(500) == "500 B"
    assert format_bytes(2048) == "2.0 KB"
    assert format_bytes(3 * 1024 * 1024) == "3.0 MB"


def test_format_rate_appends_per_second():
    assert format_rate(1024) == "1.0 KB/s"


# ── availability ──────────────────────────────────────────────────────────────

def test_available_false_when_proc_stat_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sysinfo, "PROC", tmp_path / "no-such-proc")
    assert sysinfo.available() is False
