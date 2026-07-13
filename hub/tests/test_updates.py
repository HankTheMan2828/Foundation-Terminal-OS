"""Update-system backend (docs/UPDATE-SYSTEM.md) — parsing, version compare,
and the transport-policy gate. Pure logic; no network, no curses."""
import unittest

from foundationhub import updates


class ReleaseFileTests(unittest.TestCase):
    def test_full_file(self):
        info = updates.parse_release(
            "version=v0.1.0\n"
            "built=2026-07-13\n"
            "profile=zenbook-duo-2024\n"
            "history=installed 2026-07-13 v0.1.0\n"
            "history=updated 2026-07-20 v0.1.1\n")
        self.assertEqual(info["version"], "v0.1.0")
        self.assertEqual(info["built"], "2026-07-13")
        self.assertEqual(info["profile"], "zenbook-duo-2024")
        self.assertEqual(len(info["history"]), 2)
        self.assertTrue(info["history"][1].startswith("updated"))

    def test_missing_file_is_honest(self):
        info = updates.parse_release("")
        self.assertEqual(info["version"], "unversioned")
        self.assertEqual(info["history"], [])

    def test_junk_lines_ignored(self):
        info = updates.parse_release("# comment\nnot a kv line\nversion=x\n")
        self.assertEqual(info["version"], "x")


class VersionCompareTests(unittest.TestCase):
    def test_tuple(self):
        # Current scheme (v0.1.x first stable line).
        self.assertEqual(updates.version_tuple("v0.1.0"), (0, 1, 0))
        self.assertEqual(updates.version_tuple("v1.2.10"), (1, 2, 10))
        # Legacy pre-stable tags remain readable for upgrade compare.
        self.assertEqual(updates.version_tuple("TerminalOS-v0.0.24"), (0, 0, 24))
        self.assertIsNone(updates.version_tuple("unversioned"))

    def test_newer(self):
        self.assertTrue(updates.is_newer("v0.1.1", "v0.1.0"))
        self.assertFalse(updates.is_newer("v0.1.0", "v0.1.0"))
        self.assertFalse(updates.is_newer("v0.1.0", "v0.1.1"))
        # 0.1.10 > 0.1.9 — numeric, not lexicographic.
        self.assertTrue(updates.is_newer("v0.1.10", "v0.1.9"))
        # First stable supersedes any legacy 0.0.x install.
        self.assertTrue(updates.is_newer("v0.1.0", "TerminalOS-v0.0.24"))

    def test_unversioned_machine_takes_any_release(self):
        self.assertTrue(updates.is_newer("v0.1.0", "unversioned"))
        self.assertTrue(updates.is_newer("v0.1.0", "dev-89fcdba"))

    def test_unparsable_release_never_offered(self):
        self.assertFalse(updates.is_newer("garbage", "v0.1.0"))
        self.assertFalse(updates.is_newer("", "unversioned"))


class PolicyTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updates.parse_policy("transports = usb\n"), "usb")
        self.assertEqual(
            updates.parse_policy("# comment\ntransports=usb+wired+wireless\n"),
            "usb+wired+wireless")

    def test_garbage_never_widens_policy(self):
        # Unreadable/invalid values fall to the shipped default, which does
        # NOT include wireless.
        self.assertEqual(updates.parse_policy(""), updates.POLICY_DEFAULT)
        self.assertEqual(updates.parse_policy("transports = everything"),
                         updates.POLICY_DEFAULT)
        self.assertNotIn("wireless", updates.parse_policy("transports=junk"))

    def test_comment_stripped(self):
        self.assertEqual(
            updates.parse_policy("transports = usb  # locked down\n"), "usb")


class TransportGateTests(unittest.TestCase):
    def test_usb_only_blocks_network(self):
        err = updates.transport_check("usb", iface="eth0", wireless=False)
        self.assertIn("USB", err.upper())

    def test_wired_route_passes_wired_policy(self):
        self.assertIsNone(
            updates.transport_check("usb+wired", iface="enp1s0", wireless=False))

    def test_wireless_route_blocked_unless_opted_in(self):
        err = updates.transport_check("usb+wired", iface="wlan0", wireless=True)
        self.assertIsNotNone(err)
        self.assertIn("wlan0", err)
        self.assertIsNone(updates.transport_check(
            "usb+wired+wireless", iface="wlan0", wireless=True))

    def test_no_route_is_a_clear_message(self):
        err = updates.transport_check("usb+wired", iface="", wireless=None)
        self.assertIn("route", err)


if __name__ == "__main__":
    unittest.main()
