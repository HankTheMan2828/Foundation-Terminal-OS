# Frank — Local Guardian AI + Negotiable Lockouts (design)

Status: **designed + built this pass (2026-07-06)**, offline-safe with fakes;
a real Granite Guardian endpoint is a `TODO(model)` drop-in. Read alongside
[`ARCHITECTURE.md`](ARCHITECTURE.md) ("Three tiers, one enforcement path" and
"AI integrations are separate trust domains") and [`FRANK-VOICE.md`](FRANK-VOICE.md).

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

## Model choice — IBM Granite Guardian (small)

Granite Guardian is a purpose-built **risk/safety classifier**: given a piece of
text and a risk category, it returns a Yes/No risk judgement (with a probability).
That is exactly Frank's `Sifter` job — a *sensor*, not a judge — so it slots into
the interface `frank/frankd/ai.py` already defines. A small Guardian (~2–3 B,
Q4) fits in ~1.5–2.5 GB; it is run through a **local OpenAI-compatible inference
server** (llama.cpp / vLLM) that Frank talks to over `127.0.0.1`. No weights ship
in this repo; the endpoint is config (`[sift] backend = "local"`).

BitNet b1.58 (ternary, ~0.4 GB) is noted as an even-lighter alternative for the
*voice/phrasing* role, but the **detection** sensor is Guardian because it is
trained for the classification task.

## The functions this adds

### 1. `LocalGuardianSifter` — the detection sensor (rules-bounded)
`frank/frankd/ai.py`. Implements the existing `Sifter` protocol. For each raw
activity/shell/browser line and each configured risk category, it asks the local
Guardian endpoint "is this `<category>`?" and turns a positive above a probability
threshold into a `SiftFinding` (category, confidence, excerpt, reasoning). It is
selected by `build_sifter()` when `[sift] backend = "local"`; `"cloud"` keeps the
old Mistral `ChatSifter`; `"offline"`/unconfigured keeps the `OfflineSifter`
no-op. **Nothing about the decision changes:** SiftFindings are still only
sensor readings — they become a `Finding` **only** when the Overseer's
deterministic `Rulebook` thresholds cross (`overseer.py`). The model never
decides guilt or severity. This is what lets a 2 B model be safe here.

### 2. Watching for harm — to the user *and* the system
Guardian's categories are mapped to Frank's two tracks (`ai.GUARDIAN_CATEGORIES`):

| Guardian category | Frank track | Intent |
|---|---|---|
| `harm`, `violence`, `sexual_content`, `unethical_behavior` | legal_ethical | harmful/unsafe content |
| `harm_to_system` (destructive-command intent) | security | harm to the machine |
| `self_harm` | legal_ethical → **care path** | harm to the *user* |

Realtime rules (`rules.d/*.toml`) were also expanded/tightened this pass (see
`security.toml` / `legal-ethical.toml`) so day-to-day activity is classified
even with the model off. **Frank's side always wins:** the Overseer can produce
a `Finding` of any track/severity that runs through the *same* `Enforcer` as the
rules — there is no path by which the general Hub rules or the operator override
it.

### 3. The LLM + rules decide *when* Frank speaks — baked lines stay
The [line bank](FRANK-VOICE.md) is unchanged and remains the verbatim voice.
Two decision points now gate it:
- **Enforcement reactions** (warn/lockout) speak exactly as before — rule-decided.
- **Care messages**: a harm-to-*user* signal (self-harm category / `care-*`
  rules) is `OBSERVE` severity — it deliberately never warns or locks (a punitive
  lockout in a bad moment is the wrong response). Instead Frank may send a
  **supportive** baked line. Whether it speaks is a rule gate (is this a care
  category?) optionally sharpened by Guardian confidence; the *words* are always
  from the bank. See `mistral.care_line()`.

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
3. An **advisor** (Guardian, or offline: a conservative deterministic heuristic)
   reads the plea and returns a *stance* — accept/deny, a sincerity score, and an
   abuse flag. This is **advisory only**.
4. The **rulebook** turns stance + gates into a **bounded** reduction:
   each accepted plea removes at most `per_attempt_reduction_fraction` of the
   original sentence, total reductions can never drop the end below a hard
   **floor** (`floor_fraction` of the sentence is always served), abusive pleas
   are denied and consume an attempt. Frank can always refuse; the user can never
   force release.
5. Frank answers with a baked negotiation line (the reserved
   *"You are being frank with me. I am being frank with you."* family), optionally
   AI-phrased under the same opt-in as other commentary.

The hard-ceiling / severity→duration / time-of-day→reset invariants are all
untouched — negotiation only ever *shortens* a session lock toward its floor, and
runs through the enforcer that owns those invariants.

## What is real vs. stubbed
- Sifter/negotiation **logic, gates, math, wiring, IPC, Hub client + screen**:
  built + unit-tested, offline-safe.
- The **Guardian weights + local server**: not shipped — `TODO(model)`; point
  `[sift] base_url` at a llama.cpp/vLLM Guardian endpoint to activate.
- The **root VT locker** showing the negotiation prompt during an *enforced*
  machine lock stays `TODO(hardware)` (same status the locker's DRM takeover
  already had); session-scope negotiation works through the Hub today.

## Config surface (root-only, `/etc/frank/config.toml`)
`[sift]` backend/base_url/model/threshold/categories · `[negotiation]`
enabled/max_attempts/min_served_fraction/floor_fraction/per_attempt_reduction_fraction.
All root-only, loaded once at startup — the operator still has **no** tunable
knob (spec §6).
