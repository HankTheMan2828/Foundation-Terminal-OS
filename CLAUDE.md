# Project Rules — new-computer-land (Foundation TerminalOS)

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

## See also
- `docs/ARCHITECTURE.md`, `docs/BUILD-SPEC.md`, `docs/STATUS.md`, `docs/OPEN-QUESTIONS.md`
