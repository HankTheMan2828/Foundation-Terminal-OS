# Multi-User Model

Decided 2026-07-01 (supersedes the earlier "autologin straight to the Hub"
decision — see OPEN-QUESTIONS.md §6). These terminals are shared company
machines: boot lands on a **login screen**, not the Hub.

## The rules

- **8 accounts per machine, full stop.** (`accounts.MAX_ACCOUNTS`.) The login
  screen shows the roster; when the machine is full, registration closes.
- **Fixed storage per account — no more, no less.** The allotment is set by
  the account's tier and enforced with filesystem quotas (soft = hard).
- **Tiers are employee levels.** Draft table (amounts `TODO(approval)`, the
  model itself is decided):

  | Tier | Allotment | Provisioning |
  |---|---|---|
  | GUEST | 64 MB | self-service at the terminal, password optional |
  | EMPLOYEE | 5 GB | technician setup code required |
  | SENIOR | 15 GB | technician setup code required |
  | TECHNICIAN | 25 GB | technician setup code required |

- **The setup code is `1234` for now** — an explicit placeholder. The real
  design is a company **user-ID system**: creating any above-guest account
  will require presenting a user ID. `Account.user_id` is reserved for it,
  and the registration flow is stepped so the ID-presentation step slots in
  without rework.
- **Auth is password now, ID-card/user-ID later** (decided). Three failed
  passwords = a 30-second cooldown on that account.

## How it's built (scaffold reality)

- **Registry:** `/etc/foundationhub/users.json` — root writes, the Hub reads
  (`root:operator 0640`). Password + setup-code hashes are salted
  PBKDF2-SHA256, pure stdlib. Dev override: `FOUNDATIONHUB_USERS=<path>` makes the
  registry directly writable, so the whole flow runs off-target.
- **Registration:** the Hub pre-validates for UX, but the authoritative path
  is the root helper `foundationhub-account` via `pkexec`, allowed by a polkit rule
  scoped to exactly that program. The helper revalidates capacity, username
  rules, and the setup code, then creates the Linux user and applies the
  tier quota (`setquota`, `TODO(hardware)`: quota-enabled `/home`).
- **Session layering (interim):** the Linux user `operator` hosts the
  console session; foundationhub accounts are *logical* users on top of it. The Hub
  publishes the active account to `/run/foundationhub/active-user` so Frank
  attributes events per person. Real per-account Linux sessions (PAM /
  `loginctl` user switch at the greeter) are the target design —
  `TODO(hardware)`. Until then, per-user notes/data live namespaced under the
  shared data dir; `FOUNDATIONHUB_USER=<name>` starts a session pre-authenticated
  (the hook that per-user sessions will use).
- **Hardening note (future):** with the registry group-readable, one user
  could offline-attack teammates' password hashes. Acceptable for the
  scaffold; the fix (verification moving into a root auth helper, registry
  going `0600`) should ride along with the PAM work.

## Frank in a multi-user world (decided)

**Per-user records; machine locks global.**

- Every event carries the logical user; warning scores, session lockouts,
  and incident records are keyed per person (`enforcement.UserEnforcers` —
  a router over the same single `Enforcer` path, so the hard-ceiling/
  scope/duration invariants are unchanged).
- A **SESSION**-scope lockout follows the *person*: their session is torn
  down and the login screen refuses that account until the timer expires.
  Everyone else can still sign in.
- A **MACHINE**-scope lockout (SERIOUS) freezes the terminal for everyone —
  the machine itself is compromised territory — and still survives reboots.
- The login screen learns about locks from `/run/frank/login.locks`, a
  public file carrying **usernames and expiry timestamps only** — same
  disclosure philosophy as the timestamp ledger: when, never why.
- Users can NOT see each other's data; users have NO power over Frank —
  both unchanged from the single-user model.
