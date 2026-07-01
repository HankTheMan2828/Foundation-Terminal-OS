# Status — what's real vs. stubbed

Honest tracking of the scaffold against the spec's build order (§11). Updated as
work lands. This is a skeleton pass: the structure is end-to-end and the two
testable cores (Home Hub nav, Frank rule engine) actually run; most leaf
behaviors are stubs with clear TODOs.

Legend: ✅ working · 🟨 skeleton/partial · ⬜ stub/placeholder · ⏸ deferred

## Build order (§11)

| # | Item | State | Notes |
|---|------|-------|-------|
| 1 | Base Arch install, linux-lts, minimal packages | 🟨 | `install/00`,`install/01`, `install/packages.txt`. Scripts written; not run on hardware yet. |
| 2 | Verify second-screen on chosen kernel | ⬜ | Cannot verify off-device. Device-specific; gate now lives in `profiles/zenbook-duo-2024/install.sh`, not the generic core. |
| 3 | cage + kitty kiosk, boot past any DM | 🟨 | `install/02`, `system/.../getty autologin`, `zenhub-session`. |
| 4 | Plymouth text theme, GRUB cleanup | 🟨 | `install/03`, `theme/plymouth/`. |
| 5 | Custom curses TUI shell (nav skeleton) | ✅ | `hub/zenhub` runs now: `python3 -m zenhub`. All 7 areas navigable. |
| 6 | Zenbook hardware scripts | 🟨 | Moved to `profiles/zenbook-duo-2024/hardware/`, ported to wlr-randr; keyboard-detach event hook present. Not hardware-tested. Applied only via `HARDWARE_PROFILE=zenbook-duo-2024` — see `docs/PROFILES.md`. |
| 7 | Fix NOPASSWD sudo → polkit | 🟨 | `profiles/zenbook-duo-2024/system/etc/polkit-1/rules.d/50-zenbook-backlight.rules` + scoped helper. |
| 8 | Home Hub sub-areas | 🟨 | All screens exist; Functions/Settings/Programs/Notes/Log wired to real actions or clear stubs; Recreation reads a config list; AI Chat offline-gated. |
| 9 | Frank: rules → Mistral → enforcement → ledger | 🟨 | Rule engine ✅ + unit-tested. Enforcement state machine ✅ + tested. Mistral client 🟨 offline-safe. Ledger 🟨. Daemon wiring 🟨 with stub data sources. **Operator has zero power over Frank:** read-only IPC ✅ tested, no sensitivity knob, root `frank-enforcer` applies lockouts (session vs. machine reboot semantics ✅ tested), machine locks survive reboot. The root locker's VT/DRM takeover is `TODO(hardware)`. |
| 9b | Frank AI layer: sorting/sifting + Overseer (this session) | 🟨 | Raw base-log store (`eventlog.py`) ✅ + tested. Sorting Frank (`triage.py`) ✅ + tested: stats aggregation offline, content sift via a pluggable `ai.Sifter` (offline no-op without a key, same philosophy as Mistral commentary). The Overseer (`overseer.py`) ✅ + tested: periodic check-in + immediate SERIOUS-finding trigger, both feeding synthetic Findings through the **same** `Enforcer.process()` as the rule engine — no parallel enforcement path, so the hard ceiling/scope invariants apply unchanged. Model choice for the sift/overseer roles is `TODO(approval)` — see `docs/OPEN-QUESTIONS.md`; both default to offline (no-op / never-flag) until a key is configured, same fallback posture as Mistral commentary. |
| 9c | Multi-user login + tiered accounts (this session) | 🟨 | Vision finalized — see `docs/USERS.md` + `OPEN-QUESTIONS.md` §6/§10. Login screen (`hub/zenhub/screens/login.py`) ✅ off-device: roster of ≤8, password auth w/ cooldown, stepped registration (guest self-service; setup code `1234` for higher tiers). Registry (`accounts.py`) ✅ PBKDF2, tier quotas drafted. Frank per-user ✅ + tested (`UserEnforcers`: records follow the person, machine locks global; public login.locks file). Root glue 🟨: `zenhub-account` helper + polkit rule + scope-aware `frank-enforcer`; real per-user Linux sessions + quota enforcement are `TODO(hardware)`. |
| 10 | Sound + CRT visual pass | ⬜ | `sounds/`, `theme/` have structure + hooks; assets are placeholders. |
| 11 | Soak testing | ⬜ | Not started; needs hardware. |
| 12 | In-house app replacements (decided 2026-07-01) | ⬜ | Hybrid model locked (`OPEN-QUESTIONS.md` §10): notes suite first (in-Hub editor + browser), then file manager/monitor as Hub screens, `zenmedia` as a separate program. cmus/mpv already dropped; ranger/btop/nvim are marked interim. |

## What actually runs today (no hardware needed)

- `cd hub && python3 -m zenhub` — boots to the LOGIN screen; register an
  account (setup code `1234` above guest) and sign in. Dev knobs:
  `ZENHUB_USERS=<path>` for a writable registry, `ZENHUB_USER=<name>` to skip
  login.
- `cd frank && python3 -m pytest` — rule engine, enforcement (now incl.
  per-user `UserEnforcers` + lockstate v2/public-summary tests), triage,
  Overseer (78 tests total).
- `python3 -m frankd.rules --selftest` — dumps how sample events are classified.

## Known gaps / TODO markers

Search the tree for `TODO(hardware)`, `TODO(frank)`, `TODO(approval)`:

- `TODO(hardware)` — needs the physical Zenbook to verify/finish.
- `TODO(frank)` — real data-source collectors and Mistral prompt tuning.
- `TODO(approval)` — waiting on your decision in `OPEN-QUESTIONS.md`.

## Deferred (spec §9)

- ⏸ Disk encryption / USB-boot tamper resistance.
- ⏸ Local-model Frank fallback (interface exists, no implementation).
- ⏸ Idle screensaver (explicitly none — terminal just sits).
- ⏸ **Portability tiers 2 and 3** (console-mode backend for low-power hardware;
  a from-scratch embedded/pre-MMU port). No code yet — design note only. See
  "Future portability tiers" in `docs/PROFILES.md`.
