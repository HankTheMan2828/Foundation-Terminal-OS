"""Headless tests for Programs → WEB ACCESS launch planner."""
from __future__ import annotations

from foundationhub import webaccess
from foundationhub.app import _web_launch_status


def _which_map(present: set[str]):
    return lambda name: f"/usr/bin/{name}" if name in present else None


class TestDisplayAvailable:
    def test_wayland(self):
        assert webaccess.display_available({"WAYLAND_DISPLAY": "wayland-0"})

    def test_x11(self):
        assert webaccess.display_available({"DISPLAY": ":0"})

    def test_neither(self, monkeypatch):
        monkeypatch.setattr(webaccess.os.path, "isdir", lambda p: False)
        assert not webaccess.display_available({})


class TestGuiStackReady:
    def test_wrapper_alone(self):
        assert webaccess.gui_stack_ready(_which_map({"foundationhub-web"}))

    def test_firefox_and_sway_without_wrapper(self):
        # Pieces present, but ready() still true only via wrapper OR both
        # binaries — gui_stack_ready treats firefox+sway as ready for messaging.
        assert webaccess.gui_stack_ready(_which_map({"firefox", "sway"}))

    def test_firefox_only_not_ready(self):
        assert not webaccess.gui_stack_ready(_which_map({"firefox"}))


class TestPlanLaunch:
    def test_offline_blocks(self):
        plan = webaccess.plan_launch(
            online=False,
            which=_which_map({"foundationhub-web", "firefox", "w3m"}))
        assert not plan.ok
        assert plan.argv is None
        assert "NO NETWORK" in plan.error

    def test_prefers_firefox_wrapper_over_w3m(self):
        """Real browser wins when the kiosk wrapper is installed."""
        plan = webaccess.plan_launch(
            online=True,
            which=_which_map({"foundationhub-web", "firefox", "w3m", "sway"}),
        )
        assert plan.ok
        assert plan.mode == "gui"
        assert plan.argv[0] == "foundationhub-web"
        assert webaccess.DDG_HOME in plan.argv
        assert plan.argv[0] != "w3m"

    def test_wrapper_argv_is_binary_and_url(self):
        plan = webaccess.plan_launch(
            online=True,
            which=_which_map({"foundationhub-web"}))
        assert plan.argv == ["foundationhub-web", webaccess.DDG_HOME]

    def test_custom_url(self):
        plan = webaccess.plan_launch(
            online=True,
            which=_which_map({"foundationhub-web"}),
            url="https://example.com/")
        assert plan.argv == ["foundationhub-web", "https://example.com/"]

    def test_text_fallback_when_no_gui(self):
        plan = webaccess.plan_launch(
            online=True, which=_which_map({"w3m"}))
        assert plan.ok
        assert plan.mode == "text"
        assert plan.argv == ["w3m", webaccess.DDG_HTML]
        assert "-v" not in plan.argv

    def test_force_text_skips_wrapper(self):
        plan = webaccess.plan_launch(
            online=True,
            gui=False,
            which=_which_map({"foundationhub-web", "w3m"}))
        assert plan.mode == "text"
        assert plan.argv[0] == "w3m"

    def test_force_gui_without_stack_errors(self):
        plan = webaccess.plan_launch(
            online=True,
            gui=True,
            which=_which_map({"w3m"}))
        assert not plan.ok
        assert plan.mode == "none"
        assert "NO BROWSER" in plan.error or "NO FIREFOX" in plan.error

    def test_force_gui_firefox_no_sway(self):
        plan = webaccess.plan_launch(
            online=True,
            gui=True,
            which=_which_map({"firefox"}))
        assert not plan.ok
        assert "sway" in plan.error.lower() or "COMPOSITOR" in plan.error

    def test_force_gui_firefox_sway_no_wrapper(self):
        plan = webaccess.plan_launch(
            online=True,
            gui=True,
            which=_which_map({"firefox", "sway"}))
        assert not plan.ok
        assert "LAUNCHER" in plan.error or "foundationhub-web" in plan.error

    def test_firefox_without_kiosk_incomplete_message(self):
        plan = webaccess.plan_launch(
            online=True,
            which=_which_map({"firefox"}))
        assert not plan.ok
        assert "INCOMPLETE" in plan.error or "NO BROWSER" in plan.error

    def test_no_browser_at_all(self):
        plan = webaccess.plan_launch(
            online=True, which=_which_map(set()))
        assert not plan.ok
        assert "NO BROWSER" in plan.error

    def test_lynx_fallback(self):
        plan = webaccess.plan_launch(
            online=True, which=_which_map({"lynx"}))
        assert plan.mode == "text"
        assert plan.argv[0] == "lynx"

    def test_status_hint_offline(self):
        assert webaccess.status_hint(online=False) == "offline"

    def test_status_hint_gui(self):
        hint = webaccess.status_hint(
            online=True,
            which=_which_map({"foundationhub-web", "w3m"}),
        )
        assert "Firefox" in hint
        assert "Ctrl+Q" in hint

    def test_status_hint_text(self):
        assert webaccess.status_hint(
            online=True,
            which=_which_map({"w3m"}),
        ) == "text browser · q quit"


class TestWebLog:
    """Persistent diagnostic log reader behind Logs → WEB ACCESS LOG."""

    def test_path_honors_xdg_state_home(self, tmp_path):
        p = webaccess.web_log_path({"XDG_STATE_HOME": str(tmp_path)})
        assert p == str(tmp_path / "foundationhub-web.log")

    def test_missing_log_is_empty(self, tmp_path):
        assert webaccess.read_web_log(env={"XDG_STATE_HOME": str(tmp_path)}) == []

    def test_reads_tail(self, tmp_path):
        (tmp_path / "foundationhub-web.log").write_text(
            "\n".join(f"line {i}" for i in range(10)) + "\n")
        env = {"XDG_STATE_HOME": str(tmp_path)}
        assert webaccess.read_web_log(env=env)[-1] == "line 9"
        assert webaccess.read_web_log(limit=3, env=env) == [
            "line 7", "line 8", "line 9"]


class TestWebLaunchStatus:
    """Status-bar line built from the foundationhub-web diagnostic log."""

    def test_clean_exit_no_log_is_silent(self, tmp_path):
        assert _web_launch_status(str(tmp_path / "missing.log"), 0) == ""

    def test_clean_exit_quiet_log_is_silent(self, tmp_path):
        log = tmp_path / "web.log"
        log.write_text("12:00:00 start url=x\n12:00:05 firefox-exit: clean\n")
        assert _web_launch_status(str(log), 0) == ""

    def test_clean_exit_recovered_error_is_silent(self, tmp_path):
        # Xorg failed but a later path worked — stale ERROR must not surface.
        log = tmp_path / "web.log"
        log.write_text("12:00:00 ERROR: Xorg/xinit failed rc=1\n"
                       "12:00:10 firefox-exit: clean mode=wayland\n")
        assert _web_launch_status(str(log), 0) == ""

    def test_clean_exit_with_fallback_reports(self, tmp_path):
        # w3m exiting 0 must still tell the operator the GUI failed.
        log = tmp_path / "web.log"
        log.write_text(
            "12:00:00 ERROR: all GUI paths failed — falling back to w3m\n"
            "12:00:01 fallback: w3m https://html.duckduckgo.com/html/\n")
        msg = _web_launch_status(str(log), 0)
        assert msg != ""
        assert "fallback" in msg.lower() or "falling back" in msg.lower()

    def test_failed_exit_reports_last_error(self, tmp_path):
        log = tmp_path / "web.log"
        log.write_text("12:00:00 ERROR: firefox not installed — need package\n")
        msg = _web_launch_status(str(log), 1)
        assert "firefox not installed" in msg
        assert "12:00:00" not in msg   # timestamp stripped for the 80-col bar

    def test_failed_exit_without_log_reports_returncode(self, tmp_path):
        msg = _web_launch_status(str(tmp_path / "missing.log"), 3)
        assert "3" in msg
