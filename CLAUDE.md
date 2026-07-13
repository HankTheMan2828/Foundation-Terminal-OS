# Project Rules — Foundation-Terminal-OS (Foundation TerminalOS)

> GitHub: `HankTheMan2828/Foundation-Terminal-OS` (renamed 2026-07-02 from
> `new-computer-land` — update any lingering references you find).

## Branching policy — SINGLE MAINLINE ONLY (read this first)

This repo is kept as **one long-lived branch: `Terminal-OS-Main`** (the default branch).
The operator (Henry) wants exactly one line to look at — no branch proliferation.

**Rules for every session:**
- Do all work directly on `Terminal-OS-Main`. It is the source of truth and the default branch.
- **Do NOT create long-lived `claude/*` (or any other) feature branches.** If you must make a
  throwaway branch for a specific operation, delete it as soon as you are done. Never leave it on `origin`.
- **Do NOT leave a merge half-finished.** If you start a merge, either resolve all conflicts and
  commit it, or `git merge --abort`. Never hand off a working tree that still contains conflict
  markers (`<<<<<<<`) — a later session will mistake it for "the current version."
- When asked to "clean up branches," collapse everything back to `Terminal-OS-Main` and delete the rest.

**History note:** On 2026-07-02 the repo was consolidated from ~9 stray `claude/*` branches down to the
single `Terminal-OS-Main`. The trigger was a stray unfinished merge (of an older `frank-overseer-rules`
branch that would have regressed `foundationhub` naming back to `zenhub`). Do not recreate that mess.

## Naming
- The OS is **Foundation TerminalOS**. Current in-house app namespace is `foundationhub` (NOT the old
  `zenhub` — that name was renamed away and should not reappear).

## Release tags
- Semver: **`vMAJOR.MINOR.PATCH`**. First stable line is **`v0.1.x`** (e.g. `v0.1.0`).
- Pushing a `v0.*` / `v1.*` tag triggers CI release builds (ISO + payload + AI runtime).
- Legacy pre-stable tags were `TerminalOS-v0.0.N` — frozen history; do not cut new ones.
- Details: `docs/VERSIONING.md`.

## See also
- `docs/ARCHITECTURE.md`, `docs/BUILD-SPEC.md`, `docs/STATUS.md`, `docs/VERSIONING.md`,
  `docs/OPEN-QUESTIONS.md`
