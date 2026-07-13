"""Headless tests for Settings → NETWORK backend (status parsing, WiFi radio)."""
from __future__ import annotations

import subprocess

from foundationhub import network


def _cp(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestParsers:
    def test_general_state(self):
        assert network.parse_nmcli_general_state("connected\n") == "connected"
        assert network.parse_nmcli_general_state(
            "connected (site only)\n") == "connected (site only)"
        assert network.parse_nmcli_general_state("") == ""

    def test_wifi_radio(self):
        assert network.parse_wifi_radio("enabled\n") == "enabled"
        assert network.parse_wifi_radio("disabled") == "disabled"
        assert network.parse_wifi_radio("maybe") == "unknown"

    def test_active_ssid(self):
        text = (
            "802-3-ethernet:activated:Wired connection 1\n"
            "802-11-wireless:activated:CoffeeShop\n"
        )
        assert network.parse_active_ssid(text) == "CoffeeShop"

    def test_active_ssid_ignores_non_wifi(self):
        text = "802-3-ethernet:activated:Office LAN\n"
        assert network.parse_active_ssid(text) == ""

    def test_classify_iface(self):
        assert network.classify_iface("") == "none"
        assert network.classify_iface("wlan0") == "wifi"
        assert network.classify_iface("wlp2s0") == "wifi"
        assert network.classify_iface("eth0") == "ethernet"
        assert network.classify_iface("enp1s0") == "ethernet"
        assert network.classify_iface("docker0") == "other"


class TestNetworkStatus:
    def test_offline_with_nmcli(self):
        def run(argv, timeout=5):
            if "radio" in argv:
                return _cp("disabled\n")
            if "STATE" in argv:
                return _cp("disconnected\n")
            return _cp("")

        snap = network.network_status(
            run=run, which=lambda n: "/usr/bin/nmcli" if n == "nmcli" else None,
            route_iface="", wireless=False)
        assert not snap.connected
        assert "OFFLINE" in snap.summary
        assert snap.wifi_radio == "disabled"

    def test_ethernet_online(self):
        def run(argv, timeout=5):
            if "radio" in argv:
                return _cp("enabled\n")
            if "STATE" in argv:
                return _cp("connected\n")
            if "connection" in argv:
                return _cp("802-3-ethernet:activated:Wired\n")
            return _cp("")

        snap = network.network_status(
            run=run, which=lambda n: "/bin/nmcli",
            route_iface="enp1s0", wireless=False)
        assert snap.connected
        assert snap.kind == "ethernet"
        assert "ethernet" in snap.summary.lower()
        assert "enp1s0" in snap.summary

    def test_wifi_online_with_ssid(self):
        def run(argv, timeout=5):
            if "radio" in argv and "wifi" in argv and len(argv) == 3:
                return _cp("enabled\n")
            if "STATE" in argv:
                return _cp("connected\n")
            if "connection" in argv:
                return _cp("802-11-wireless:activated:HomeNet\n")
            return _cp("")

        snap = network.network_status(
            run=run, which=lambda n: "/bin/nmcli",
            route_iface="wlan0", wireless=True)
        assert snap.connected
        assert snap.kind == "wifi"
        assert snap.ssid == "HomeNet"
        assert "HomeNet" in snap.summary

    def test_no_nmcli_with_route(self):
        snap = network.network_status(
            run=lambda *a, **k: _cp(),
            which=lambda n: None,
            route_iface="eth0", wireless=False)
        assert snap.connected
        assert "no nmcli" in snap.state


class TestWifiRadio:
    def test_set_on_success(self):
        calls = []

        def run(argv, timeout=5):
            calls.append(argv)
            return _cp()

        msg = network.set_wifi_radio(True, run=run, which=lambda n: "/bin/nmcli")
        assert "ON" in msg
        assert calls == [["nmcli", "radio", "wifi", "on"]]

    def test_set_off_failure(self):
        def run(argv, timeout=5):
            return _cp(stderr="not authorized", returncode=1)

        msg = network.set_wifi_radio(False, run=run, which=lambda n: "/bin/nmcli")
        assert "not authorized" in msg

    def test_missing_nmcli(self):
        msg = network.set_wifi_radio(True, which=lambda n: None)
        assert "not available" in msg

    def test_status_label(self):
        def run(argv, timeout=5):
            return _cp("enabled\n")

        assert network.wifi_radio_status(
            run=run, which=lambda n: "/bin/nmcli") == "ON"
