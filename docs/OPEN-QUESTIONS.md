# Open Decisions — Drafted for Your Review

Everything here is a **draft awaiting your approval** (spec §5 and §10). Nothing
in this file is locked. Where I had to pick something to make the scaffold run,
I picked a sensible default and marked it **[DEFAULT — change freely]**. Reply
with edits and I'll apply them.

Legend: ⬜ needs your decision · 🟨 drafted, awaiting sign-off · ✅ approved

---

## 1. Menu labels (spec §5, §10)

The Home Hub top level. Flavor mixes Vault-Tec/Aperture with plain practicality.
All labels are centralized in [`hub/zenhub/labels.py`](../hub/zenhub/labels.py)
so approving them is a single-file edit. Current drafts:

| Area (spec name)   | 🟨 Draft label        | Alt option            |
|--------------------|-----------------------|-----------------------|
| (Hub title)        | `TERMINAL // MAIN`    | `OPERATOR CONSOLE`    |
| Programs           | `PROGRAMS`            | `UTILITIES`           |
| Recreation         | `RECREATION`          | `LEISURE SUBSYSTEM`   |
| Functions Control  | `FUNCTIONS`           | `SYSTEMS CONTROL`     |
| Settings           | `CONFIGURATION`       | `SETTINGS`            |
| Log                | `LOGS`                | `RECORDS`             |
| Personal Notes     | `PERSONAL FILE`       | `OPERATOR JOURNAL`    |
| AI Chat            | `ASSISTANT`           | `ADVISORY`            |

Sub-labels (Log split, Notes split, etc.) are also in `labels.py`. **Status:
🟨 awaiting sign-off — tell me a set and I'll lock it.**

## 2. Recreation game list (spec §5, §10)

Genre buckets from the spec, with concrete Arch-available titles proposed:

| Bucket             | 🟨 Proposed titles (packages)                          |
|--------------------|--------------------------------------------------------|
| Roguelikes         | NetHack (`nethack`), DCSS (`crawl` / `crawl-tiles`), Cataclysm-DDA console (`cataclysm-dda`) |
| Arcade / simple    | `nsnake` (snake), `bastet`/`vitetris` (tetris-like), `ninvaders` (invaders) |
| Puzzle / strategy  | `gnuchess` + `cchess`/`scid` front, `2048` (terminal 2048), `nudoku` (sudoku) |

Open sub-questions: ⬜ include the heavier ones (Cataclysm, DCSS tiles) or keep
it lean? ⬜ any specific titles you already love? The Recreation screen reads its
list from [`system/etc/zenhub/recreation.toml`], so adding/removing a game is a
config edit, not a code change.

## 3. Frank rule/keyword lists + severity tiers (spec §6, §10) — ✅ RESOLVED

Two category tracks, each with tiers. Rule lists live in
[`system/etc/frank/rules.d/`](../system/etc/frank/rules.d), tuned in a
dedicated refinement session (operator Q&A, see git history on the
`security-rules-refinement` branch for the full back-and-forth).

- `security.toml` — offensive-tooling detection split into four rules by tool
  (recon/exploit-framework/attack-tooling/raw-listener) so severity could be
  set per tool instead of one bucket; exploit frameworks and destructive
  commands are `serious`, everything else operator-confirmed `elevated`. The
  old blanket `password=` text match was removed (pure false-positive noise on
  routine dev work); credential detection is now file/key-pattern only.
  Runaway-CPU detection was a **dead rule** — the collector never emitted the
  marker it looked for — now fixed: 85% sustained for 10s (per-process streak
  tracked in `frankd/sources.py`), severity `minor`.
- `legal-ethical.toml` — now covers piracy (torrent keywords only — the
  DRM-tool/yt-dlp half was dropped, too false-positive prone), adult content
  (`serious`), gambling (`elevated`), illegal-goods/drug purchase-intent
  (`minor`, deliberately narrow), self-harm content (a new `observe` severity
  tier — logged, but the warn/lockout pipeline is bypassed entirely so a bad
  moment never triggers a punitive lockout), and a narrow direct-violent-threat
  rule (`elevated`). A broader hate-speech/extremism word list was
  **intentionally not authored** — the operator wants that handled by a
  scheduled/periodic AI-layer review instead of realtime keyword matching;
  that's parked as a follow-up for the AI-layer session, not this one.
  ⚠️ Adult-content/gambling/drug rules target `sources = ["browser", ...]`,
  but the browser collector is still an unfilled stub (see parking lot) — real
  day-to-day web coverage isn't active until that's built.
- Enforcement tuning (`frankd/config.py`): lockout durations halved from the
  original first draft (minor 2.5min/elevated 7.5min/serious 15min session or
  machine, 30min hard ceiling). Warning threshold unchanged (3 warnings then
  lockout on the 4th). New: a track's accrued warning score now decays back to
  zero if that track has gone quiet for 5+ minutes, so scattered one-offs
  don't slowly stack toward a lockout the way a burst does.

See the top of each rules file for the tier model
(`observe` / `minor` / `elevated` / `serious`) and how tiers map to warning counts and
lockout scope.

## 4. Frank voice lines / commentary style guide (spec §6, §10)

Tone is locked by the spec: **cold, corporate, procedural, faintly
threatening — "this is being recorded and evaluated," not comic snark.** A
starter style guide + example lines are in
[`docs/FRANK-VOICE.md`](FRANK-VOICE.md). These double as few-shot examples for
the Mistral prompt and as offline fallback lines when no API key is set.
**Status: 🟨 drafted — review the voice and the examples.**

## 5. Frank sensitivity — ✅ RESOLVED: operator has NO power over Frank

**Superseded by your explicit direction: the operator cannot have ANY power
over Frank, ever.** The previously-drafted in-Settings sensitivity dial has been
**removed entirely** — no Settings screen, no IPC command, no operator-editable
file. This overrides the spec §5 line about exposed sensitivity tuning.

Sensitivity still exists as a detection parameter, but it is a **root-only**
value in `/etc/frank/config.toml` (root:frank, operator can't read it), loaded
once at startup. Changing it requires root, which the operator account does not
have and has no path to. The 1–5 model still governs how the middle severity
tier flexes (see `frankd/rules.py`), but only someone with root can set it.

Enforcement was also moved out of the operator's reach: lockouts are applied by
the root `frank-enforcer` service, not rendered by the operator-owned Hub, so
the operator cannot ignore or no-op a lockout. See ARCHITECTURE.md →
"Enforcement is root-owned." ⬜ Only open sub-question: what should the root-set
default sensitivity be? (currently 3 / balanced).

## 6. Login model — ✅ decided

Autologin straight to the Hub (your call this session). Wired in
[`system/etc/systemd/system/getty@tty1.service.d/autologin.conf`].

## 7. Theme defaults — ✅ decided (tunable later)

Amber primary / green alt, Terminus font, scanline+glow. In
[`theme/`](../theme). Adjustable from Settings → theme once that screen is real.

## 8. Mistral key handling — ✅ decided

No key yet → offline mode. Rule engine runs fully offline; AI commentary and AI
Chat show a clear "no key configured" state. Key loading is scaffolded from
root-owned secret files; nothing secret is committed. See
[`docs/INSTALL.md`](INSTALL.md) → "Configuring API keys."

---

## Parking lot (raised by the spec, not yet needed)

- Local-model fallback for Frank (spec §6) — architected as a swappable
  `Commentator` interface now, not implemented in v1.
- Disk encryption / USB-boot tamper resistance (spec §6, §9) — deferred phase,
  intentionally out of scope.
