# Open Decisions — Drafted for Your Review

Everything here is a **draft awaiting your approval** (spec §5 and §10). Nothing
in this file is locked. Where I had to pick something to make the scaffold run,
I picked a sensible default and marked it **[DEFAULT — change freely]**. Reply
with edits and I'll apply them.

Legend: ⬜ needs your decision · 🟨 drafted, awaiting sign-off · ✅ approved

---

## 1. Menu labels (spec §5, §10) — ✅ LOCKED (2026-07-01)

The operator approved the primary draft set; the alternate options are
dropped. The locked set, all in
[`hub/foundationhub/labels.py`](../hub/foundationhub/labels.py): `TERMINAL // MAIN`,
`PROGRAMS`, `RECREATION`, `FUNCTIONS`, `SYSTEM STATUS`, `LOGS`,
`PERSONAL FILE`, `ASSISTANT`, plus the new login-screen set
(`TERMINAL // ACCESS` etc.). Future edits are ordinary changes, not pending
decisions.

**✅ Settings → System Status, approved and applied.** The user decided the
old Settings/Configuration area shouldn't exist as an operator-facing settings
surface at all — resource limits and user/auth actions (`passwd`) are removed
outright. What's left under `SYSTEM STATUS`: NETWORK (still launches `nmtui`),
a read-only USER line (username + uid), and a FUNCTIONS list of basic
functioning/not-functioning checks (network, audio, the Frank overseer).
THEME & SOUND moved to `FUNCTIONS` alongside the other real hardware toggles.

## 2. Recreation game list (spec §5, §10) — ✅ SUPERSEDED by the in-house mandate

The original question (which Arch packages to ship) was answered by §10's
in-house mandate: arcade titles and chess are in-house programs now
(Foundation Arcade, Foundation Chess — see STATUS row 12), so the old
proposed-package table is moot. What remains:

- **NetHack was removed entirely (operator direction 2026-07-05)** — dropped
  from `install/packages.txt`, `recreation.toml`, and the `_DEFAULT` fallback.
  The roguelike slot is covered by the two vendored Rogue vintages (feedback
  #2); the in-house roguelike (§11) remains a possible future project.
  Dungeon Crawl's menu entry was removed 2026-07-02 — `crawl` was never
  actually in `packages.txt`, so it was a dead item on a real install.
- The Recreation screen still reads
  [`system/etc/foundationhub/recreation.toml`], so list edits stay config,
  not code.

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

## 4. Frank voice lines / commentary style guide (spec §6, §10) — ✅ RESOLVED

Tone is locked by the spec: **cold, corporate, procedural, faintly
threatening — "this is being recorded and evaluated," not comic snark.** The
style guide + finalized example lines are in
[`docs/FRANK-VOICE.md`](FRANK-VOICE.md), finalized via the line-by-line
review (BUILD-QUEUE §7, completed 2026-07-02). Per the operator's standing
direction that Frank is a primarily rule-based overseer system (§5), this
line bank is now Frank's **primary voice**, not an offline fallback — AI
phrasing (`mistral.py`'s `MistralCommentator`) is a double opt-in
(`commentary.ai_enabled` + a key) that falls back to these same lines on any
misbehavior, and doubles as few-shot examples for its prompt when enabled.

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
"Enforcement is root-owned." ✅ Last sub-question closed 2026-07-02: the
root-set default sensitivity **stays 3 (balanced)** — confirmed alongside the
operator's standing direction that **Frank moves toward a primarily
rule-based overseer system** (the AI layer stays secondary; keep detection
strength in the rules, not in model judgment). Same session also fixed
`system/etc/frank/config.toml`, whose `hard_ceiling_seconds = 3600` was
silently overriding the halved 1800 decided in §3.

## 6. Login model — ✅ REVERSED (2026-07-01): multi-user login screen

The earlier "autologin straight to the Hub" call is superseded: these are
shared company terminals, so boot lands on a **login screen** — up to 8
accounts per machine, fixed per-tier storage, guest self-service,
technician setup code (placeholder `1234`) for everything above guest, and
a future company user-ID system for provisioning. Full spec:
[`docs/USERS.md`](USERS.md). The getty autologin conf survives, but it now
lands on the login screen, not the Hub; `FOUNDATIONHUB_USER=<name>` is the
skip-login hook for dev and future per-user sessions.

## 7. Theme defaults — ✅ decided (tunable later)

Amber primary / green alt, Terminus font, scanline+glow. In
[`theme/`](../theme). Adjustable from Settings → theme once that screen is real.

## 8. Mistral key handling — ✅ decided

No key yet → offline mode. Rule engine runs fully offline; AI commentary and AI
Chat show a clear "no key configured" state. Key loading is scaffolded from
root-owned secret files; nothing secret is committed. See
[`docs/INSTALL.md`](INSTALL.md) → "Configuring API keys."

## 9. AI-layer session (sorting/sifting Frank + the Overseer) — 🟨 partially resolved

The three-tier Frank model is built and tested — see
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) "Three tiers, one enforcement path."
What was decided vs. what's still open:

- ✅ **Primarily rule-based, per the operator's standing direction (§5).**
  The Overseer's verdicts now come from a deterministic `Rulebook`
  (threshold rules in root-only `config.OverseerConfig`: sift-accumulation,
  slow-burn, burst) that behaves identically on every machine, online or
  off. AI is reduced to (a) the Sifter, a classification *sensor* whose
  readings only become findings via those thresholds, and (b) an Overseer
  *second opinion* that is OFF by default (`overseer.ai_enabled`), consulted
  only when the rulebook found nothing, and can add but never veto. Frank's
  voice defaults to the approved line bank (`commentary.ai_enabled` opt-in
  for AI phrasing). With both flags off — the default — nothing in Frank's
  loop touches a network.
  ⬜ Sub-question: the rulebook thresholds shipped with defaults (confidence
  ≥ 0.75; 1/2/5 confident sift findings → minor/elevated/serious; 12
  same-track incidents per period → elevated; 10 incidents across ≥3 rules
  around a SERIOUS finding → serious). Tune freely — root-only config.
- ✅ **Same hard ceiling applies to the Overseer** (not an exception to it).
  The Overseer expresses every decision as a `Finding` run through the exact
  `Enforcer.process()` the rule engine uses — no parallel enforcement path,
  so it structurally cannot exceed the ceiling, scope, or duration rules
  already governing Frank.
- ✅ **Check-in cadence:** the Overseer's periodic path runs twice a day
  (`config.OverseerConfig.checkin_interval_seconds`, default 12h) — a config
  value, tune freely.
- ✅ **Immediate-trigger scope:** only a SERIOUS-severity finding wakes the
  Overseer early; lesser lockouts/warnings wait for the next scheduled
  check-in (`config.OverseerConfig.wake_on_serious`).
- ⬜ **Model choice for the two AI roles — still open** (and now lower
  stakes: the Sifter is a sensor behind deterministic thresholds, and the
  Overseer brain is off unless you flip `overseer.ai_enabled`), same as
  sensitivity was left as a config value rather than hardcoded. Both roles
  default to the existing Mistral integration's wire shape (`ai.py`'s
  `ChatCompletionClient`, OpenAI/Mistral-style `/v1/chat/completions`) so
  nothing new has to be stood up to try it, but the model string is a config
  change either way. Researched recommendations, based on how each role is
  actually used:

  | Role | Call frequency | What it needs | Suggestion |
  |---|---|---|---|
  | Sifter (`triage.py`) | Every triage interval (default every 15 min) — the frequent one | Fast, cheap text classification against one narrow category | A small/fast-tier model. If moving off Mistral: **Claude Haiku 4.5** ($1/$5 per MTok, 200K context) — cheapest Claude tier, sized for exactly this kind of frequent narrow classification. |
  | Overseer brain (`overseer.py`) | A couple of times a day, plus rare SERIOUS triggers — the infrequent one | Judgment over an already-organized digest; consequential (can trigger a machine-wide lockout) | Call volume is low enough that per-token price barely matters — absolute monthly cost stays small either way. Favor capability: **Claude Opus 4.8** ($5/$25 per MTok, 1M context) for the strongest judgment, or **Claude Sonnet 5** ($3/$15, $2/$10 intro through 2026-08-31) as a cheaper near-Opus alternative if the extra margin isn't worth it. |

  Mistral was the first thing that came to mind when the rest of Frank was
  scaffolded, not a considered choice for these two specific roles — hence
  leaving this open rather than silently picking one. Note: the Anthropic API
  uses a different request/response shape than the OpenAI/Mistral-style
  `chat/completions` `ai.py` speaks today — adopting Claude for either role
  means adding a second concrete class behind the same `Sifter`/
  `OverseerBrain` Protocol, not adapting the existing one.

## 9b. Official naming — ✅ DECIDED (2026-07-01)

The system's official name is **Foundation TerminalOS**, tagline **"From the
Foundation."** Applied to README, package descriptions, and the UI branding
constants (`labels.BRAND` / `labels.TAGLINE` — the Hub and login subtitles
carry the brand; the login screen shows the tagline). The repo/install path
`/opt/terminal-os` is plumbing, not branding, and stays.

## 10. In-house applications mandate + web integration (2026-07-01 session)

The operator's finalized vision, decided in one pass:

- ✅ **Everything user-facing goes in-house.** The open-source stand-ins
  (ranger, btop, nvim, the games) are placeholders to be replaced, not kept.
  **Hybrid architecture:** core apps (notes, file manager, system monitor)
  become native Hub screens; heavy apps (media playback, games) become
  separate in-house TUI programs the Hub launches.
- ✅ **Redundancy cuts approved:** ONE in-house media player (`foundationmedia`,
  audio+video — cmus and mpv both dropped from the package set); ONE editor
  everywhere (the notes suite's editor becomes the system editor; nvim is
  interim-only); LOGS is confirmed as the single records surface (system
  records + overseer ledger, nothing duplicated elsewhere); labels locked
  (§1).
- ✅ **foundationmedia playback backend — APPROVED (2026-07-01, BUILD-QUEUE §4):**
  the operator picked the hybrid, option (c): a fully in-house core (pure-stdlib
  WAV/AIFF decode + ALSA PCM output via ctypes, no external programs) plus
  **ffmpeg as an optional broad-format decode *engine*** under the in-house UI
  (mp3/flac/ogg/opus/m4a/…). Without ffmpeg the player still runs, WAV/AIFF-only
  — that stdlib path is the Pocket8086-tier fallback. ffmpeg is treated as a
  build tool under our UI, not a borrowed app. Audio v1; video stays out of
  scope (console tier may never do it). *Built 2026-07-01 — see STATUS row 12.*
  curses editor plus a note browser — dated journal, tagged notes, search by
  tag/text — all inside the Hub. No external editor. *Built 2026-07-01
  (BUILD-QUEUE §1); nvim retired — see STATUS row 12.*
- ✅ **Web integration: none in v1.** The terminal stays offline-first. The
  chosen future direction is a **retrieval terminal** backed by a search API
  — operator's candidates: **Kagi API or Brave Search API** (AI-mediated
  access was considered and is less likely). Both are plain HTTPS+JSON, so
  the feature stays viable on the console-mode portability tier. Design the
  Hub so a NETWORK ARCHIVE area can be added without rework.
- ✅ **Multi-user login + tiers + per-user Frank** — see §6 and
  [`docs/USERS.md`](USERS.md).
- ✅ Per-tier quota amounts (GUEST 64 MB / EMPLOYEE 5 GB / SENIOR 15 GB /
  TECHNICIAN 25 GB) and tier names **approved 2026-07-02** — see USERS.md.
- ⬜ The real user-ID provisioning system (replaces the `1234` setup code) —
  future session.

## 11. Roguelike design (BUILD-QUEUE §5 item 3) — 🟨 design doc drafted, awaiting approval

Full design: [`docs/ROGUELIKE-DESIGN.md`](ROGUELIKE-DESIGN.md). Per the
operator's ask: **three games, one engine** — faithful re-implementations of
**both classic vintages** of Rogue (the og code exists: recovered by the
original authors and BSD-3-licensed; we port the *rulebook* to pure-stdlib
Python, not the C), plus **Foundation Depths**, a restrained modernization
with the Aperture/Vault facility flavor. Retires nethack + crawl. No code
until the doc is approved. Decisions (details in the doc §5):

- ✅ **Vintages — operator decided (2026-07-01): both.** Rogue **5.4.4
  (1985)** as the default, **3.6 (1981, the OG)** as a second ruleset
  behind the same ROGUE title screen ("I want the OG still but the 85
  version looks nicer").
- ✅ **Classic names stay verbatim (2026-07-02):** the og games ship as
  **ROGUE**, no Foundation rebranding — "it's a tribute to history
  changing games."
- ✅ **Score boards — machine-wide shared (2026-07-02):** the authentic
  original behavior; a deliberate, narrow exception to the per-user-data
  rule (name + score only). USERS.md carries the exception note.
- ⬜ Name for the modernized game (proposed: **Foundation Depths**) — the
  2026-07-02 answer locked the classics' names but didn't pick the new
  game's.
- ⬜ Confirm BSD-attributed re-implementation counts as in-house
  (ship the authors' notice + on-screen credit).
- ⬜ Classic input: original commands + arrows only (recommended).
- ⬜ Sign off the Depths flavor register (facility premise, announcer voice,
  terminals-as-lore, section themes) and the modernization list (doc §3.3 —
  closed list; anything not on it is out).

## 12. Update system — trust decisions (feedback item 11) — 🟨 built with the recommended defaults; sign-off still wanted

Full design + implementation status: [`docs/UPDATE-SYSTEM.md`](UPDATE-SYSTEM.md).
Same-day operator direction (2026-07-04) was to implement rather than wait,
so the code carries every **[RECOMMENDED]** default below; each ⬜ stays open
in the sense that changing your mind is a config/small-code change, and
**signing (the first item) is genuinely not built yet** — checksum-over-HTTPS
only until you pick. The mechanics (USB = UPDATE mode on the release ISO;
network = Settings → SYSTEM UPDATE; per-machine transport policy defaulting
to `usb+wired`, wireless opt-in from Settings; no persistent daemon) are in
the doc:

- ⬜ **What verifies an update?** The release already carries `SHA256SUMS`
  for the ISO, and the network payload would get one too — but a checksum
  fetched from the same place as the payload proves integrity, not origin
  (the trust anchor is GitHub + TLS). Options:
  - (a) HTTPS + checksum only — simplest, trusts GitHub.
  - (b) **[RECOMMENDED]** add a detached **minisign/signify signature**: one
    project keypair, public key baked into the installed OS at install time,
    every release artifact signed in CI. Tiny single-binary verifier, no GPG
    daemon — fits DOS-grade minimalism. Key rotation ships as a signed
    update; a lost key means machines update by USB until reinstalled.
  - (c) full pacman-key/GPG signing of the package repo too — heaviest,
    probably overkill while the offline repo is already `SigLevel Never` by
    design.
  - USB path either way: possession of the stick is the credential
    (consistent with spec §6 placing physical access out of scope) — but the
    same signature can be verified on the embedded payload as a corruption/
    tamper check before applying. Include it?
- ⬜ **Who may trigger an update?**
  - USB path: whoever can boot the machine from USB (physical access).
    Gate it further (setup code before UPDATE proceeds)? Recommendation:
    no extra gate — physical is already the boundary, and the flow is
    non-destructive.
  - Network path: recommendation — **TECHNICIAN tier + setup-code
    re-entry**, mechanically a polkit rule scoped to exactly
    `start foundation-update.service` (fixed root logic, verified payload,
    no operator-influenced inputs). Stricter alternative on the table:
    network path only **notifies** that an update exists, applying always
    requires the USB stick (zero new operator→root paths at all).
  - Explicitly NOT Frank-gated: Frank observes and can flag, but update
    authority stays a human/tier decision — keeping with "Frank decides
    violations, not system administration." Confirm?
- ⬜ **Who may change the transport policy** (including the wireless
  opt-in)? Recommendation: TECHNICIAN tier, setup-code gated, written
  through a root helper in the existing `foundationhub-account` pattern —
  `/etc/foundation-update.conf` itself stays root-owned. In a company
  deployment that means employees/guests can *see* the policy but only a
  technician can loosen it.
- ⬜ **Network payload scope (v1):** recommendation — network updates carry
  the **OS payload only** (repo tree, ~MB); Arch base-package upgrades stay
  USB-only, because the ISO's offline repo is the *tested* package set and
  rolling mirrors would drift machines onto untested versions. A release
  needing new packages flags `requires-usb` and the screen says so honestly.
  Sign off or widen.
- 🟥 **HARD RULE for sign-off — no update path may weaken Frank isolation.**
  Stated as testable invariants in UPDATE-SYSTEM.md §6: no new
  operator→root path (except, if approved, the one scoped oneshot start);
  Frank state never reset — found while designing:
  **`install/05-frank.sh` currently truncates `lockout.state` on re-run**,
  so a naive re-run update would clear an active machine lockout; the fix
  (no-clobber guard; lockouts survive updates and re-arm on the post-update
  boot) is part of the design, §4.1. Isolation checks re-run at the end of
  every update, failure = failed update. Approve the invariant list.

---

## Parking lot (raised by the spec, not yet needed)

- Local-model fallback for Frank (spec §6) — architected as a swappable
  `Commentator` interface now, not implemented in v1. The same pattern now
  also covers `ai.py`'s `Sifter`/`OverseerBrain` interfaces (§9).
- Disk encryption / USB-boot tamper resistance (spec §6, §9) — deferred phase,
  intentionally out of scope.
