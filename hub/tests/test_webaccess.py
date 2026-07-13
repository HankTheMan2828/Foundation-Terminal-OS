"""Headless tests for Programs → WEB ACCESS launch planner."""
from __future__ import annotations

from foundationhub import webaccess


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


class TestGuiOptIn:
    def test_default_off(self):
        assert not webaccess.gui_opted_in({})

    def test_on(self):
        assert webaccess.gui_opted_in({"FOUNDATIONHUB_WEB_GUI": "1"})
        assert webaccess.gui_opted_in({"FOUNDATIONHUB_WEB_GUI": "yes"})


class TestPlanLaunch:
    def test_offline_blocks(self):
        plan = webaccess.plan_launch(
            online=False, which=_which_map({"firefox", "w3m"}))
        assert not plan.ok
        assert plan.argv is None
        assert "NO NETWORK" in plan.error

    def test_prefers_text_even_when_firefox_and_display(self):
        """Text wins even if firefox + Wayland exist — never auto-launch GUI."""
        plan = webaccess.plan_launch(
            online=True,
            which=_which_map({"firefox", "w3m"}),
            env={"WAYLAND_DISPLAY": "wayland-0"},
        )
        assert plan.ok
        assert plan.mode == "text"
        assert plan.argv[0] == "w3m"
        assert webaccess.DDG_HTML in plan.argv
        # Must not pass -v (that is w3m --version and exits immediately).
        assert "-v" not in plan.argv

    def test_w3m_argv_is_just_binary_and_url(self):
        plan = webaccess.plan_launch(
            online=True, which=_which_map({"w3m"}))
        assert plan.argv == ["w3m", webaccess.DDG_HTML]

    def test_gui_only_when_forced(self):
        plan = webaccess.plan_launch(
            online=True, gui=True,
            which=_which_map({"firefox", "w3m"}))
        assert plan.ok
        assert plan.mode == "gui"
        assert plan.argv[0] == "firefox"
        assert webaccess.DDG_HOME in plan.argv

    def test_gui_opt_in_env_with_display(self):
        plan = webaccess.plan_launch(
            online=True,
            which=_which_map({"firefox", "w3m"}),
            env={"FOUNDATIONHUB_WEB_GUI": "1",
                 "WAYLAND_DISPLAY": "wayland-0"},
        )
        # Text still wins when both are present — only gui=True forces GUI
        # ahead of text. Opt-in env is for when text is missing.
        assert plan.mode == "text"

    def test_gui_opt_in_when_no_text_browser(self):
        plan = webaccess.plan_launch(
            online=True,
            which=_which_map({"firefox"}),
            env={"FOUNDATIONHUB_WEB_GUI": "1",
                 "WAYLAND_DISPLAY": "wayland-0"},
        )
        assert plan.mode == "gui"
        assert plan.argv[0] == "firefox"

    def test_no_browser_at_all(self):
        plan = webaccess.plan_launch(
            online=True, which=_which_map(set()))
        assert not plan.ok
        assert "NO TEXT BROWSER" in plan.error or "NO BROWSER" in plan.error

    def test_lynx_fallback(self):
        plan = webaccess.plan_launch(
            online=True, which=_which_map({"lynx"}))
        assert plan.mode == "text"
        assert plan.argv[0] == "lynx"

    def test_status_hint_offline(self):
        assert webaccess.status_hint(online=False) == "offline"

    def test_status_hint_text(self):
        assert webaccess.status_hint(
            online=True,
            which=_which_map({"w3m", "firefox"}),
            env={"WAYLAND_DISPLAY": "wayland-0"},
        ) == "DuckDuckGo · text"
