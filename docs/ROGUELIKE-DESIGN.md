# Roguelike Design — BUILD-QUEUE §5 item 3 (DRAFT for operator approval)

**Status: ⬜ AWAITING OPERATOR APPROVAL — no code has been built.** This doc is
the deliverable of the Fable 5 design session; the implementation sessions
that follow it (Sonnet 5 per BUILD-QUEUE) build exactly what is approved here.
Open decisions are marked ⬜ and mirrored in `OPEN-QUESTIONS.md` §11.

Retires: **NetHack and Dungeon Crawl** — the last open-source stand-ins in
`recreation.toml`, and the last interim item in STATUS.md row 12.

---

## 1. The operator's ask, restated

> "I would like the original Rogue if possible (if you can find the og code),
> then one that is a little more modernized, but not too much."

The og code exists, and we can legally use it. In 1999 the original authors —
Michael Toy, Ken Arnold, and Glenn Wichman — released the recovered source of
**Rogue 5.4.4** (the final classic Unix version, ~1985) under a **BSD
3-clause license**. It is preserved at:

- https://github.com/RoguelikeRestorationProject/rogue5.4 (canonical
  restoration; the org also preserves 3.6 and 5.2)
- https://github.com/Davidslv/rogue (a maintained mirror of 5.4.4;
  `LICENSE.TXT` carries the authors' BSD grant)

BSD 3-clause permits derivative works with attribution. We do **not** ship or
port the C code (pure-stdlib Python + curses is the law here); we re-implement
in Python, using the 5.4.4 source as the **authoritative mechanics reference**
— every table, formula, and message checked against the original files
(`fight.c`, `monsters.c`, `things.c`, `rooms.c`, `command.c`, …).

**Operator amendment (2026-07-01):** ship *both* classic vintages — the OG
**Rogue 3.6** (1981) *and* **Rogue 5.4.4** (1985, "looks nicer"). They are
two table-sets on one classic engine, not two engines (see §2.2).

So the plan is **three games, one package, one shared engine**:

| Game | What it is | Retires |
|---|---|---|
| **ROGUE — 1985** (classic, default vintage) | Faithful re-implementation of Rogue 5.4.4, the authors' finished version. Unimproved on purpose. | nethack |
| **ROGUE — 1981** (classic, OG vintage) | Faithful re-implementation of Rogue 3.6, the Berkeley original — same engine, the 1981 tables. | (same) |
| **FOUNDATION DEPTHS** (⬜ name) | Same engine, restrained modernization, Aperture/Vault facility flavor. | crawl |

The classic game is also the modern game's skeleton: Depths is a content and
QoL layer over an engine whose correctness was proven by matching the
original. This is why classic ships first.

## 2. Games A & B — ROGUE (classic, two vintages)

### 2.1 What "faithful" means

**Replicated exactly (from the 5.4.4 source):**

- **Goal & structure** — descend to level 26+, take the Amulet of Yendor,
  climb back out. Permadeath. One dungeon, no branches.
- **Level generation** (`rooms.c`, `new_level.c`) — up to 9 rooms on the 3×3
  grid, "gone" rooms, dark rooms (likelier deeper), maze rooms on deep
  levels, corridors, doors, secret doors/passages, the trap table
  (trapdoor, bear trap, sleeping gas, arrow, poison dart, teleport, rust)
  with the original placement odds.
- **The 26 monsters A–Z** (`monsters.c`) — stats, level ranges, treasure
  odds, and every special power: the aquator rusting armor, the rattlesnake
  draining strength, the wraith draining levels, the leprechaun's gold
  grab, the nymph's theft, the xeroc's disguise, the ice monster's freeze,
  the medusa's confusion, mean-monster aggression flags — the table ports
  verbatim.
- **Items & identification** (`things.c`, `init.c`) — potions, scrolls,
  rings, wands/staffs with the original effect lists and probabilities;
  unidentified appearances (potion colors, gem rings, wood/metal staffs)
  shuffled per game; scroll titles generated from the original syllable
  list; `c`all to name things; cursed items; the scare-monster scroll on
  the floor; food and the hunger clock (Hungry/Weak/Faint) at the original
  rates; the nine armors with original AC; the original weapon table and
  throwing rules.
- **Combat & character math** (`fight.c`, `player stats`) — the to-hit
  roll, the strength table with 18/xx percentiles, damage strings,
  experience table, HP regen daemon. Rogue's "daemons and fuses" scheduler
  is re-implemented as-is (it's a lovely, testable design).
- **Interface** — the classic 80×24 layout: message line up top with
  `--More--`, map, status line (`Level: Gold: Hp: Str: Arm: Exp:`) below.
  The full original command set from `command.c` (`hjklyubn` moves +
  shifted runs, `s`earch, `q`uaff, `r`ead, `w`ield, `W`ear, `P`ut on,
  `z`ap, `t`hrow, `d`rop, `i`nventory, `>` `<`, `^`, `c`all, `D`iscoveries,
  `S`ave, `Q`uit, …). Arrow keys added as aliases — the only input
  concession.
- **Death & glory** — the tombstone (RIP screen), the top-ten score board,
  save-and-exit with the save file **deleted on load** (the original's
  anti-scumming rule, which is also our permadeath integrity rule).

**Deliberate deviations (all forced by the platform, none gameplay-visible):**

- Python + curses re-implementation, not a C port. Python's RNG, so runs
  aren't bit-identical to a 1985 VAX — but every *distribution* matches.
- No `!` shell escape (this OS does not hand out shells) and no wizard
  mode in the shipped game (a `FOUNDATION_ROGUE_DEBUG` env hook may exist
  for dev only).
- Save format is our own JSON per user, not the original binary state.
- Colors: the original was monochrome; we draw through `foundationhub.theme`
  semantic pairs, which on the amber CRT *is* a 1980 terminal. Classic mode
  uses the normal pair for nearly everything — no rainbow retrofit.
- Score board is per-user, not machine-wide (see §5 ⬜).

### 2.2 Two vintages — ✅ DECIDED (operator, 2026-07-01): ship both

**5.4.4 (1985)** is the version the authors finished, the one virtually
every later "rogue" port descends from, and the nicer one to play — it is
the **default vintage** and gets built first (§2.1 is written against it).

**3.6 (1981)** is the OG — the Berkeley original, preserved at
https://github.com/RoguelikeRestorationProject/rogue3.6 under the same BSD
grant. Structurally it's the same game (same 3×3 generator, same goal, same
identification play), so it lands as a **second ruleset on the classic
engine**, its tables and messages transcribed from the 3.6 source in its own
session (R4) — divergences taken from the two source trees side by side,
never from memory. The visible differences are part of the charm: the 1981
bestiary is the unapologetically D&D-flavored one (kobolds, floating eyes,
rust monsters, invisible stalkers, umber hulks…) that the 5.x era replaced
with original creatures (aquators, quaggas, xerocs…), and the later
refinements (e.g. maze rooms) aren't there yet — it's the rawer, meaner
1981 experience, preserved as-is.

**Presentation:** one recreation.toml entry, **ROGUE**, whose title screen
offers the vintage — `1985` highlighted by default, `1981` below it,
each labeled with its year and provenance line. Saves and score boards are
kept per vintage (a 1981 run is not comparable to a 1985 run).

Both restorations compile on modern systems, so during implementation we
run the real things side-by-side and check behavior empirically, not just
by reading C.

## 3. Game B — FOUNDATION DEPTHS (modernized, but not too much)

### 3.1 Premise

Sublevels of a decommissioned Foundation facility. The elevator only goes
down. Somewhere below Sublevel 26 sits the **Archive Core** — bring it back
up. A dry facility announcer (cold, corporate, procedural — the house
register, but explicitly *not* Frank: no ledger data, no Frank surfaces, just
flavor in the same voice family) narrates section transitions and deaths.
"Thank you for your compliance. Your remains will be catalogued."

### 3.2 What stays classic (the "not too much" contract)

Turn-based. Permadeath (save deleted on load). Procedural floors on the same
generator. Unidentified consumables. The hunger clock. Room-based lighting
(no fancy FOV — Rogue's model is cheap, readable, and half the tension).
ASCII glyphs. 80×24. No classes, no shops, no town, no crafting, no skill
trees, no meta-progression that changes difficulty — records are cosmetic.
No mouse. No tiles. Balance inherited from Rogue: most Depths content maps
1:1 onto a proven Rogue mechanic with new skin, so the game is fair on day
one.

### 3.3 What modernizes (the whole list — if it's not here, it's out)

1. **Color** — full use of the theme's semantic pairs: hostiles in alert,
   items in accent, the announcer dim. Still amber/green CRT, never raw
   curses colors.
2. **Message log** — a scrollable review of past messages (the single most
   painful omission in 1985).
3. **Look/examine** — a cursor to inspect any visible tile; monster and
   item descriptions with their *discovered* mechanics (never spoils
   unidentified items).
4. **Contextual key bar** — one dim line of the keys that matter right now.
   The full command reference on `?`.
5. **Small mercies** — confirm before stepping on a *known* trap; confirm
   quit; auto-pickup gold only.
6. **Death recap + records** — what killed you, the run timeline, per-user
   run history and streaks (same `FOUNDATIONHUB_DATA` pattern as arcade
   scores / chess stats).
7. **Facility terminals** — a rare `&` tile: a working terminal with a
   two-paragraph log entry. Pure flavor, found not bought, ~1 per few
   floors. This is the lore channel and the cheapest big win for tone.
8. **Content reskin + a few new pieces** — the bestiary and item lists get
   facility names and a handful of genuinely new entries (e.g., sentry
   turrets that hold a corridor — a ranged threat Rogue lacked; keycard
   doors gating one optional vault room per few floors, the card always on
   that floor). New pieces are individually approved in the content session
   before they ship.

Section themes (every ~6 sublevels the palette of monsters/flavor shifts:
Maintenance → Laboratories → Containment → Archives) give the descent a
sense of place without touching the generator's bones.

### 3.4 Explicitly rejected as "too much"

Auto-explore, minimap overlays, quest systems, NPC dialogue, factions,
unlockable characters, difficulty settings, seeds shared between users,
graphics beyond ASCII, sound. (Daily-seed runs noted as a possible far-future
recreation.toml-level addition; not in this build.)

## 4. Architecture

One new top-level package in the existing `games/` distribution, following
the arcade/chess pattern exactly:

```
games/foundation_depths/           ⬜ name — see §5
  __init__.py  __main__.py         entry; picks ruleset from argv[0]/flag
  chrome.py                        borrowed CRT bezel (same as chess/arcade)
  labels.py                        Depths strings; classic keeps Rogue's own
                                   message text in its ruleset (fidelity
                                   requires the original strings verbatim —
                                   noted deviation from the labels.py rule)
  engine/                          ── curses-free, unit-tested ──
    rng.py                         seedable RNG (determinism for tests)
    dungeon.py                     3×3 room-grid generator, traps, stairs
    schedule.py                    daemons & fuses (Rogue's own scheduler)
    creature.py  items.py          entities, inventory, identification state
    combat.py                      fight.c math (to-hit, str table, damage)
    game.py                        turn loop, command dispatch, win/death
    save.py  records.py            JSON save (delete-on-load), scores/history
  rulesets/
    classic85.py                   the 5.4.4 tables + effects, source-checked
    classic81.py                   the 3.6 tables + divergences, source-checked
    depths.py                      Depths content tables + QoL flags
  ui/                              ── curses only ──
    screen.py                      map/status/message rendering, --More--
    menus.py                       inventory menus, look cursor, log view
```

- **Two console scripts, one program:** `foundation-rogue` (title screen
  picks the vintage, 1985 default) and `foundation-depths` (added to
  `games/pyproject.toml` + `install/08-games.sh`). All three games run the
  same engine with a different ruleset.
- **Rendering & portability:** turn-based means a *blocking* `getch()` — no
  timer loop, zero idle CPU, the friendliest program in the OS for the
  console tier and Pocket8086. Redraw per turn; 80×24 minimum, larger
  terminals letterbox (classic) or extend the map viewport (Depths).
- **Per-user everything:** saves, scores, run history under the account's
  own `FOUNDATIONHUB_DATA` tree via the same helper pattern as
  `foundation_arcade/scores.py`. Saves are a few KB of JSON — quota-polite.
- **Frank:** nothing special. It's a user program on a Frank-watched
  terminal; no exemptions, no new Frank-visible surfaces, and the Depths
  announcer never echoes ledger content.
- **Attribution:** the package ships the original BSD notice
  (`LICENSE-ROGUE.txt`) and the classic title screen credits
  "Toy · Wichman · Arnold, 1980–1985". See §5 ⬜.

## 5. Open decisions — ⬜ (mirrored in OPEN-QUESTIONS.md §11)

1. ⬜ **Name the modernized game.** Proposed: **FOUNDATION DEPTHS**
   (package `games/foundation_depths/`, script `foundation-depths`).
   Alternates if wanted: SUBLEVELS, THE STACKS, FOUNDATION VAULTS.
2. ✅ **Vintages — DECIDED (operator, 2026-07-01): both.** 5.4.4 (1985) is
   the default; 3.6 (1981, the OG) ships as a second ruleset behind the
   same title screen. See §2.2.
3. ⬜ **BSD attribution under the in-house mandate.** The classic game is a
   from-scratch Python re-implementation, but it knowingly derives its
   design and text from BSD-licensed source, so we keep the authors'
   notice and credit them on screen. Confirm you're happy calling that
   in-house (recommended: yes — the mandate's point is no borrowed
   *programs*; this borrows a 45-year-old rulebook, lawfully).
4. ⬜ **Score boards.** Original Rogue's top-ten was machine-wide, but
   USERS.md says accounts never see each other's data. Default: **per-user
   top-ten** (recommended). Say the word if you want an opt-in shared
   board instead — it's authentic, but it's a deliberate exception.
5. ⬜ **Classic input:** original commands verbatim with arrow keys as the
   only addition (recommended), or also allow the Depths key bar in
   classic (not recommended — museum piece).
6. ⬜ **Depths flavor register** (§3.1–3.3): sign off on the facility
   premise, announcer voice, terminals-as-lore, and section themes.

## 6. Implementation plan (multiple sessions, Sonnet 5)

| Session | Builds | Done when |
|---|---|---|
| **R1 — skeleton dungeon** | package scaffold, RNG, generator, movement, lighting/memory, stairs, rendering, blocking input loop | you can walk all 26 levels of a legible dungeon |
| **R2 — classic systems** | monsters + AI, combat math, items + identification, hunger, daemons/fuses, traps, saves | winnable/losable Rogue minus polish |
| **R3 — classic polish + fidelity audit** | full command set, tombstone, top ten, --More--, side-by-side checks against compiled 5.4.4, **wire in: recreation.toml + _DEFAULT get ROGUE, retire nethack** (packages.txt, STATUS) | ROGUE (1985) ships |
| **R4 — the 1981 vintage** | `classic81.py` transcribed from the 3.6 source (bestiary, items, messages, divergences), vintage title screen, per-vintage saves/scores, side-by-side audit against compiled 3.6 | both vintages behind one ROGUE entry |
| **R5 — Depths** | ruleset + content tables (bestiary/items approved in-session), QoL layer (log, look, key bar, recap), terminals, section themes | Depths playable end to end |
| **R6 — balance + close-out** | play-balance pass, records/history UI, tests to green, **retire crawl**, STATUS row 12 closes | §5 item 3 complete |

**Tests throughout** (the engine is curses-free by construction): generator
invariants on thousands of seeded levels (connectivity, stairs reachable,
room bounds), combat math against tables transcribed from `fight.c`, hunger
and regen daemon timing, identification shuffle correctness, save round-trip
+ delete-on-load, score ordering. Frank's suite untouched and green.

## 7. What this session did NOT do

No game code, no scaffold, no recreation.toml/packages.txt changes. NetHack
and Dungeon Crawl stay in place until R3/R5 retire them. Next step is yours:
approve or amend §5, then open an R1 session.
