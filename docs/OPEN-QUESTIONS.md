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

## 3. Frank rule/keyword lists + severity tiers (spec §6, §10)

Two category tracks, each with tiers. Starter lists live in
[`system/etc/frank/rules.d/`](../system/etc/frank/rules.d). These are
**deliberately conservative first drafts** — real tuning needs your input on
what should trip a flag for *your* actual usage.

- `security.toml` — malware/exploit tooling keywords, credential-exposure
  patterns, unsafe-script patterns, runaway-resource thresholds.
- `legal-ethical.toml` — the broader "concerning content/activity" track.

⬜ **This is the biggest genuinely-open item.** The scaffold ships plausible
examples so the engine is testable, but the actual pattern lists and thresholds
are yours to define. See the top of each file for the tier model
(`minor` / `elevated` / `serious`) and how tiers map to warning counts and
lockout scope.

## 4. Frank voice lines / commentary style guide (spec §6, §10)

Tone is locked by the spec: **cold, corporate, procedural, faintly
threatening — "this is being recorded and evaluated," not comic snark.** A
starter style guide + example lines are in
[`docs/FRANK-VOICE.md`](FRANK-VOICE.md). These double as few-shot examples for
the Mistral prompt and as offline fallback lines when no API key is set.
**Status: 🟨 drafted — review the voice and the examples.**

## 5. Frank sensitivity range exposed in Settings (spec §5, §6, §10)

The spec allows exactly one user-tunable Frank knob in Settings: **detection
sensitivity threshold only** — everything else (rules, logs, functions) is
hard-locked and unreachable.

🟨 **Draft:** a single 1–5 sensitivity dial.

| Level | Meaning                              | Effect on tiers |
|-------|--------------------------------------|-----------------|
| 1     | Lenient                              | only `serious` flags act; more warnings before lockout |
| 3     | **[DEFAULT]** balanced               | tiers as authored |
| 5     | Strict                               | `elevated` acts like `serious`; fewer warnings |

The dial only shifts *thresholds/warning counts*, never reveals rules, never
disables Frank, and can't push any lockout past the hard cooldown ceiling. ⬜
Confirm the 1–5 model and what the endpoints should mean.

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
