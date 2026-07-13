# Versioning & release naming

Foundation TerminalOS uses **semantic versioning** on Git tags:

```
vMAJOR.MINOR.PATCH
```

## Current line: `0.1.x` (first stable)

| Tag example | Meaning |
|-------------|---------|
| `v0.1.0` | First operator-declared stable release of the OS |
| `v0.1.1`, `v0.1.2`, … | Patch / incremental releases on the stable line |
| `v0.2.0` | Next minor when a larger feature set lands as a line |
| `v1.0.0` | Reserved for a future major milestone (not yet planned) |

**How a release is cut**

1. Land work on `Terminal-OS-Main`.
2. Push a tag matching `v0.*` or `v1.*` (e.g. `git tag v0.1.0 && git push origin v0.1.0`).
3. CI (`.github/workflows/build-iso.yml` + `build-ai-binary.yml`) builds the
   installer ISO, network payload, checksums, and attaches the USB creators
   to a GitHub Release of the same name.

The installed machine records that tag in `/etc/foundation-release` (see
[`UPDATE-SYSTEM.md`](UPDATE-SYSTEM.md) §2). Settings → SYSTEM STATUS and
SYSTEM UPDATE show it; version compare is numeric on the triple, so
`v0.1.10` > `v0.1.9`.

## Legacy scheme (frozen)

Pre-stable development used:

```
TerminalOS-v0.0.N
```

Examples: `TerminalOS-v0.0.1` … `TerminalOS-v0.0.24`. Those tags remain in
git history and on old machines; they are **not** used for new cuts. The
update compare path still parses them, so a machine on
`TerminalOS-v0.0.24` correctly offers `v0.1.0` as an upgrade
(`(0,1,0) > (0,0,24)`).

## Package versions in-tree

Python package versions in `hub/`, `frank/`, `games/`, and `media/`
`pyproject.toml` track the OS minor line (`0.1.0` at first stable). They
are install metadata, not the release tag; the OS identity that users see
is always the git/CI tag stamped into `VERSION` → `/etc/foundation-release`.
