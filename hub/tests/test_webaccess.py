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
        # Force no socket dir either.
        monkeypatch.setattr(webaccess.os.path, "isdir", lambda p: False)
        assert not webaccess.display_available({})


class TestPlanLaunch:
    def test_offline_blocks(self):
        plan = webaccess.plan_launch(
            online=False, gui=True, which=_which_map({"firefox", "w3m"}))
        assert not plan.ok
        assert plan.argv is None
        assert "NO NETWORK" in plan.error

    def test_prefers_gui_when_display(self):
        plan = webaccess.plan_launch(
            online=True, gui=True,
            which=_which_map({"firefox", "w3m"}))
        assert plan.ok
        assert plan.mode == "gui"
        assert plan.argv[0] == "firefox"
        assert webaccess.DDG_HOME in plan.argv

    def test_falls_back_to_text_without_display(self):
        plan = webaccess.plan_launch(
            online=True, gui=False,
            which=_which_map({"firefox", "w3m"}))
        assert plan.ok
        assert plan.mode == "text"
        assert plan.argv[0] == "w3m"
        assert webaccess.DDG_HTML in plan.argv

    def test_text_when_gui_missing_even_with_display(self):
        plan = webaccess.plan_launch(
            online=True, gui=True,
            which=_which_map({"w3m"}))
        assert plan.ok
        assert plan.mode == "text"
        assert plan.argv[0] == "w3m"

    def test_no_browser_at_all(self):
        plan = webaccess.plan_launch(
            online=True, gui=False, which=_which_map(set()))
        assert not plan.ok
        assert "NO TEXT BROWSER" in plan.error

    def test_no_browser_with_display(self):
        plan = webaccess.plan_launch(
            online=True, gui=True, which=_which_map(set()))
        assert not plan.ok
        assert "NO BROWSER" in plan.error

    def test_chromium_also_gui(self):
        plan = webaccess.plan_launch(
            online=True, gui=True,
            which=_which_map({"chromium"}))
        assert plan.mode == "gui"
        assert plan.argv[0] == "chromium"

    def test_status_hint_offline(self):
        assert webaccess.status_hint(online=False) == "offline"

    def test_status_hint_gui(self):
        assert webaccess.status_hint(
            online=True, gui=True,
            which=_which_map({"firefox"})) == "DuckDuckGo · gui"

    def test_status_hint_text(self):
        assert webaccess.status_hint(
            online=True, gui=False,
            which=_which_map({"w3m"})) == "DuckDuckGo · text"
