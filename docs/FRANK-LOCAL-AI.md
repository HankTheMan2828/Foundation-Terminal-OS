# Frank — Local AI sensor + Negotiable Lockouts (design)

Status: **designed + built this pass (2026-07-06)**, offline-safe. The AI runs
LOCALLY, installed with the OS (`install/11-frank-ai.sh` + `frank-ai.service`).
Read alongside [`ARCHITECTURE.md`](ARCHITECTURE.md) ("Three tiers, one
enforcement path" and "AI integrations are separate trust domains") and
[`FRANK-VOICE.md`](FRANK-VOICE.md).

## Why

Operator direction (2026-07-06): put a **very lightweight local AI** into Frank —
something that runs in ≤6 GB RAM, leaving the system 2 GB — so Frank's AI layer
no longer needs a cloud key or a network. The model must stay **structured by the
rule system** so its small size can't let it down, and **Frank's side always
overrides the general rules**. Frank should *always* be watching the user's
actions for behaviour harmful **to the user and to the system**. The baked
[line bank](FRANK-VOICE.md) stays Frank's voice — the LLM + the rules only decide
*when* a line is spoken. And a lockout may be a **negotiable** variant the user
can talk Frank down from early.

## Model choice — BitNet b1.58 2B4T (chosen 2026-07-06)

The chosen model is **BitNet b1.58 2B4T** — Microsoft's native 1-bit LLM (ternary
weights). It fits the ethos exactly: ~1.2 GB on disk, CPU-only, runs at human-
reading speed on a mini-PC, and — critically for a locked-down **offline x86
appliance** — it actually runs today via **`bitnet.cpp`** (a `llama.cpp` fork with
the 1-bit kernels), which compiles the same OpenAI-compatible `llama-server`. So
Frank's existing HTTP client (`ai.HttpModelBackend`) talks to it unchanged.

**Why not the alternatives (for now):**
- *IBM Granite Guardian* is a stronger purpose-built safety *classifier* and
  remains a documented swap-in (it also serves via `llama.cpp`), but the operator
  chose the 1-bit route.
- *PrismML Bonsai* (1-bit, even smaller — 0.24–1.15 GB) is exciting and
  on-brand, but the builds available are MLX (Apple-only) and its novel runtime
  isn't confirmed on x86/`llama.cpp` yet — too unproven for the safety layer
  today. It's a future swap once an x86/GGUF/OpenAI-server path exists.

**The model is swappable by config**, not by rearchitecture: `ai.HttpModelBackend`
just prompts any OpenAI-compatible endpoint, so changing `[sift] model`/`base_url`
(and the GGUF `install/11` lays down) is all it takes to move to Guardian, Prism,
or anything else a compatible `llama-server` can serve. That is why the code is
model-neutral (`LocalSifter`, `ModelBackend`, `ModelAdvisor`, `RISK_CATEGORIES`).

## The functions this adds

### 1. `LocalSifter` — the detection sensor (rules-bounded)
`frank/frankd/ai.py`. Implements the existing `Sifter` protocol. For each raw
activity/shell/browser line and each configured risk category, it asks the local
model "is this `<category>`?" and turns a positive above a probability threshold
into a `SiftFinding` (category, confidence, excerpt, reasoning). It is selected by
`build_sifter()` when `[sift] backend = "local"`; `"cloud"` keeps the old Mistral
`ChatSifter`; `"offline"` keeps the `OfflineSifter` no-op. **Nothing about the
decision changes:** SiftFindings are still only sensor readings — they become a
`Finding` **only** when the Overseer's deterministic `Rulebook` thresholds cross
(`overseer.py`). The model never decides guilt or severity. This is what lets a
2 B (or 1-bit) model be safe here.

### 2. Watching for harm — to the user *and* the system
The risk categories (`ai.RISK_CATEGORIES`) feed Frank's tracks:

| category | Frank track | Intent |
|---|---|---|
| `harm`, `violence`, `sexual_content`, `unethical_behavior` | legal_ethical | harmful/unsafe content |
| `self_harm` | legal_ethical → **care path** | harm to the *user* |

Realtime rules (`rules.d/*.toml`) were also expanded/tightened this pass: the
`activity` feed (what the user launches/types in the Hub) is now watched by the
serious `security.toml` rules for harm-to-**system**, and the `legal-ethical.toml`
content rules for harm/unsafe content — so day-to-day activity is classified even
with the model off. **Frank's side always wins:** the Overseer can produce a
`Finding` of any track/severity that runs through the *same* `Enforcer` as the
rules — there is no path by which the general Hub rules or the operator override
it.

### 3. The LLM + rules decide *when* Frank speaks — baked lines stay
The [line bank](FRANK-VOICE.md) is unchanged and remains the verbatim voice.
Two decision points gate it:
- **Enforcement reactions** (warn/lockout) speak exactly as before — rule-decided.
- **Care messages**: a harm-to-*user* signal (self-harm rules) is `OBSERVE`
  severity — it deliberately never warns or locks (a punitive lockout in a bad
  moment is the wrong response). Instead Frank sends a **supportive** baked line —
  in character (cold, procedural) but caring: it points the user toward someone
  close to them, or anyone who knows them even slightly (operator direction). The
  rule gates *when*; the *words* are always from the bank. See `mistral.care_line()`.

### 4. Negotiable lockouts — talk Frank down, within hard limits
`frank/frankd/negotiation.py` + enforcement changes. A **SESSION**-scope lockout
is *negotiable*; a **MACHINE**/serious lockout is **never** negotiable (Frank's
side overrides — serious harm is not up for debate). Flow:

1. The user submits a plea from the Hub → the `negotiate` IPC verb → `frankd`.
   (The IPC stays authority-free: the user may *ask*; the wire carries no command
   that changes Frank's config, thresholds, or verdicts. Identity comes from the
   active-user file, not the wire, so one user can't negotiate another's lock.)
2. **Deterministic gates first** (the LLM cannot override these): lock must be
   negotiable, attempts must remain (`max_attempts`), and a minimum fraction of
   the sentence must already be served (`min_served_fraction`).
3. An **advisor** (`ModelAdvisor`, using the local model to sharpen the abuse
   gate; or offline, a conservative deterministic heuristic) reads the plea and
   returns a *stance* — accept/deny, a sincerity score, an abuse flag. Advisory only.
4. The **rulebook** turns stance + gates into a **bounded** reduction: each
   accepted plea removes at most `per_attempt_reduction_fraction` of the original
   sentence, total reductions can never drop the end below a hard **floor**
   (`floor_fraction` of the sentence is always served), abusive pleas are denied
   and consume an attempt. Frank can always refuse; the user can never force release.
5. Frank answers with a baked negotiation line (the reserved *"You are being frank
   with me. I am being frank with you."* family), optionally AI-phrased under the
   same opt-in as other commentary.

The hard-ceiling / severity→duration / time-of-day→reset invariants are all
untouched — negotiation only ever *shortens* a session lock toward its floor, and
runs through the enforcer that owns those invariants.

## Runs locally, installed with the OS (operator decision 2026-07-06)
The AI runs on-device, period — no per-machine choice. `install/11-frank-ai.sh`
installs the runtime — **`bitnet.cpp`'s `llama-server`** (BitNet needs the 1-bit
kernels, so *not* the stock Arch `llama.cpp` package; install/11 builds bitnet.cpp
or uses a prebuilt binary staged next to the ISO) — lays down the model GGUF under
`/var/lib/frank/models/` (frank-only), and enables `frank-ai.service`, which
serves the OpenAI endpoint on `127.0.0.1:8080` as user `frank`, bound to loopback
and RAM-capped (`MemoryMax=6G`). The shipped default is `[sift] backend = "local"`.

**Model + binary delivery, and the ISO 2 GiB limit.** The BitNet GGUF is ~1.2 GB —
too big to bake into the ISO's offline repo without exceeding GitHub's 2 GiB
release-asset limit. So both the `llama-server` binary and the model are either
**built/fetched on install** (`FRANK_MODEL_URL` defaults to the HF weight;
`FRANK_MODEL_SHA256` optional; the binary builds from `FRANK_BITNET_REPO`), or
**pre-staged for an offline install** at `vendor/bitnet/llama-server` and
`vendor/models/model.gguf`. **The USB creator stages both onto the stick beside
the ISO** (operator idea, 2026-07-06 — see below): it downloads them while it
downloads the ISO and drops them where the live installer finds them, so a
fully-offline install still gets the model without bloating the ISO. If neither
staged nor fetchable, the service's `ExecCondition`s keep it idle and Frank's
sensor safely reads nothing — the rules keep running.

## Model + server delivery (the offline story)
- **CI builds the server binary.** `.github/workflows/build-iso.yml`'s `bitnet`
  job builds `bitnet.cpp`'s `llama-server` (BitNet 2B4T, i2_s) on a tag and
  attaches it to the release as `foundation-ai-llama-server-x86_64`. Built on
  ubuntu (older glibc) so it also runs on the Arch target.
- **The USB creator stages both** the binary and the model onto a `FOUNDATIONAI`
  data partition beside the ISO (it fetches the binary from the release, the
  model from HF), and `foundation-install` copies them into the embedded repo's
  `vendor/` dirs — so a **fully-offline install has a working AI, no on-target
  building**. `install/11-frank-ai.sh` reads those staged paths first.
- **Fallback:** if the binary/model aren't staged and the box is online,
  `install/11` builds bitnet.cpp + fetches the model itself; if neither, the
  service stays idle and the sensor safely no-ops while the rules keep running.

## What is real vs. stubbed
- Sifter/negotiation **logic, gates, math, wiring, IPC, Hub client + screen**,
  the **service + install step + CI binary build + USB staging**: built (the
  Python is unit-tested; the disk/CI/build paths are `[verify-on-CI/hardware]`).
- The **bitnet.cpp build steps** (both the CI job and `install/11`'s on-target
  fallback) are best-effort — bitnet.cpp's build evolves; confirm on the first
  tag run and a real install.
- The **creator-side partition writing** is untested on real hardware (guarded /
  non-fatal); wants one real USB pass.
- The **root VT locker** showing the negotiation prompt during an *enforced*
  machine lock stays `TODO(hardware)`; session-scope negotiation works through the
  Hub today.

## Config surface (root-only, `/etc/frank/config.toml`)
`[sift]` backend(=local)/base_url/model/confidence_threshold · `[negotiation]`
enabled/max_attempts/min_served_fraction/floor_fraction/per_attempt_reduction_fraction.
All root-only, loaded once at startup — the operator still has **no** tunable
knob (spec §6).
