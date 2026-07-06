"""The login roster (docs/USERS.md): all 8 slots always visible, unused slots
as [ CREATE NEW USER ] placeholders, per-account storage + violation readout,
and — the first-hardware-run bug — the roster re-reads the registry when
users.json changes on disk instead of requiring a device restart."""
import pytest

from foundationhub import labels, session
from foundationhub.accounts import MAX_ACCOUNTS, Registry, Tier


@pytest.fixture
def registry_path(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    monkeypatch.setenv("FOUNDATIONHUB_USERS", str(path))
    return path


def _add(path, *names):
    reg = Registry(path)
    for name in names:
        reg.add_account(name, "pw", Tier.EMPLOYEE, setup_code="1234")
    return reg


def _screen():
    from foundationhub.screens.login import LoginScreen
    return LoginScreen()


def _slot_labels(scr):
    return [i.label for i in scr.menu.items if i.label]   # drop spacing rows


def test_eight_slots_with_placeholders_and_spacing(registry_path):
    _add(registry_path, "alice", "bob")
    scr = _screen()
    slots = _slot_labels(scr)
    assert len(slots) == MAX_ACCOUNTS
    assert slots[:2] == ["alice", "bob"]
    assert slots[2:] == [labels.LOGIN_CREATE_SLOT] * (MAX_ACCOUNTS - 2)
    # One blank spacing row between every pair of slots.
    all_labels = [i.label for i in scr.menu.items]
    assert len(all_labels) == MAX_ACCOUNTS * 2 - 1
    assert all_labels[1::2] == [""] * (MAX_ACCOUNTS - 1)


def test_full_roster_has_no_placeholders(registry_path):
    _add(registry_path, *[f"user{i}" for i in range(MAX_ACCOUNTS)])
    scr = _screen()
    assert labels.LOGIN_CREATE_SLOT not in _slot_labels(scr)


def test_roster_reloads_when_registry_changes(registry_path):
    """First-hardware-run bug: an account created out-of-band (root helper,
    another console) must appear without restarting the device."""
    _add(registry_path, "alice")
    scr = _screen()
    assert "carol" not in _slot_labels(scr)
    _add(registry_path, "carol")           # out-of-band write, same file
    scr._maybe_reload()
    assert "carol" in _slot_labels(scr)


def test_account_row_shows_storage_and_violations(registry_path):
    _add(registry_path, "alice")
    scr = _screen()
    scr._violations = {"alice": 2}
    item = next(i for i in scr.menu.items if i.label == "alice")
    text = item.status()
    assert f"2 {labels.LOGIN_VIOLATIONS}" in text
    assert f"/ 5 GB" in text               # EMPLOYEE allotment, used / total


def test_locked_account_disables_and_recovers(registry_path, monkeypatch):
    _add(registry_path, "alice")
    scr = _screen()
    item = next(i for i in scr.menu.items if i.label == "alice")
    import time
    locked = {"machine_end": 0.0, "users": {"alice": time.time() + 60},
              "violations": {}}
    monkeypatch.setattr(session, "read_login_locks", lambda: locked)
    scr._refresh_locks()
    assert not item.enabled
    assert labels.LOGIN_LOCKED in item.status()
    clear = {"machine_end": 0.0, "users": {}, "violations": {"alice": 1}}
    monkeypatch.setattr(session, "read_login_locks", lambda: clear)
    scr._refresh_locks()
    assert item.enabled
    assert f"1 {labels.LOGIN_VIOLATIONS}" in item.status()
