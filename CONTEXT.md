# AI Scene Manipulation Context

This context defines how the AI participates in a live Tabletop Simulator scene. It separates generic scene manipulation from the game rules that determine whether a sequence is legal.

## Language

**Safe TTS control plane**:
The generic product boundary for inspecting and manipulating a live Tabletop
Simulator scene through explicit, bounded, evidence-backed MCP requests.
Game-playing autonomy and game-rule authority are optional layers outside this
boundary.
_Avoid_: universal game opponent, arbitrary automation, privileged observer

**Control-plane adapter**:
An optional integration, such as the HTTP AI gateway, that translates external
chat or backend requests into MCP operations while remaining subject to the
control plane's visibility, identity, planning, approval, and verification
gates.
_Avoid_: alternate authority, direct bridge mutation, safety bypass

**Generic object action**:
A bounded, allowlisted operation on a TTS object, such as moving, rotating, locking, naming, spawning, destroying, or changing container membership.
_Avoid_: Arbitrary Lua, unrestricted scene command

**AI orchestration**:
The AI's selection and sequencing of generic object actions to carry out an intended game operation.
_Avoid_: Direct game-rule enforcement, arbitrary automation

**Game rules**:
The active game's authority for deciding which state transitions and action sequences are legal.
_Avoid_: Bridge policy, object API behavior

**Game-rule adapter**:
The game-specific layer that interprets the active rules, validates intended transitions, and produces an allowed sequence of generic object actions.
_Avoid_: TTS bridge, generic object action

**Reversible scene action**:
A generic object action whose effects can normally be corrected by another bounded action or a human undo, including movement, rotation, naming, locking, and container membership changes.
_Avoid_: Destructive action, harmless action

**Host-approved scene action**:
A destructive or broad-scene action that requires explicit host approval before execution because the applicable safety policy has not authorized it automatically.
_Avoid_: Autonomous action, blanket approval

**Condition-authorized destructive action**:
A destructive scene action that may execute without per-action host approval only when a previously defined, explicit safety condition is satisfied and the action remains within its bounded scope.
_Avoid_: blanket destructive permission, inferred approval

**Plan-scoped cleanup**:
The first condition-authorized destructive action: cleanup of an object created by the same bounded plan, authorized only when server-side plan metadata records that the object was absent from the plan's baseline scene, returned from that plan's spawn operation, and still matches its expected state. The provenance is internal metadata and is not written into TTS names, descriptions, or tags.
_Avoid_: deleting pre-existing objects, broad cleanup, metadata stamping

**Destructive policy rule**:
A host-managed, versioned allowlist condition that determines whether a specific destructive action may proceed without per-action approval; the rule identifier is returned and audited, and neither the model nor the caller may create or weaken it.
_Avoid_: model-authored permission, caller-supplied exception, untracked policy drift

**Policy transition**:
A host-only change to destructive-action policy that takes effect only at a plan or session boundary and invalidates pending plans requiring destructive evaluation; no plan may continue under a different policy version.
_Avoid_: mid-plan policy drift, retroactive approval, pending-plan reuse

**Uncertainty stop**:
The execution boundary where the AI pauses instead of acting when object identity, legal state, turn ownership, preconditions, or the result of an action is not sufficiently certain.
_Avoid_: Best-effort guessing, automatic retry

**Action plan**:
A bounded, ordered sequence of generic object actions evaluated with per-step preconditions and postconditions.
_Avoid_: Unbounded macro, arbitrary script

**Scene action plan**:
An action plan containing only allowlisted live-scene object, container, zone, or placement actions; camera, screenshot, chat, and administrative save operations are separate explicit capabilities.
_Avoid_: mixed side effects, hidden communication, whole-scene replacement

**Fail-fast plan**:
The default execution rule that stops a scene action plan at the first execution, precondition, policy, identity, visibility, or post-verification failure and returns the partial result without automatic compensation.
_Avoid_: silent continuation, automatic rollback, partial success hidden as completion

**Plan budget**:
The MVP bound of at most 20 scene-action steps and 60 seconds of total execution time, with bounded per-step settling; work beyond the budget must be split into separately observed plans.
_Avoid_: unbounded macro, timeoutless physics wait, hidden long-running mutation

**Mutation serialization**:
The single-writer rule for live scene changes: plans execute exclusively, while reads may run concurrently; an intervening mutation invalidates stale preconditions rather than being merged or guessed around, and a conflicting plan is rejected rather than queued.
_Avoid_: concurrent writes, silent merge, stale-plan execution

**Single bridge owner**:
The rule that one control-plane server process owns a TTS instance's bridge and mutation stream; additional owners must fail or remain read-only rather than create independent locks.
_Avoid_: split-brain writers, process-local lock illusion, conflicting plans

**Read-only recovery**:
The post-crash or post-restart phase in which the control plane re-pings TTS, establishes a fresh scene epoch, reconciles durable in-flight or idempotent plans, and rejects mutations until reconciliation succeeds.
_Avoid_: optimistic restart writes, stale epoch reuse, automatic replay

**Uncertain-commit recovery**:
The read-only recovery path entered when a bridge disconnect or timeout prevents the control plane from knowing whether a mutation committed; it re-observes before any new action and never retries the unknown mutation automatically.
_Avoid_: blind retry, optimistic failure, duplicate commit

**Dry-run preflight**:
A non-mutating plan validation that may be optional for reversible actions and mandatory for destructive or broad-scene actions; it does not reserve scene state, and execution must repeat all identity, policy, and precondition checks.
_Avoid_: dry-run as lock, stale approval, skipped execute-time validation

**Plan invalidation**:
A change or failed verification that makes the remaining steps of an action plan unsafe or no longer applicable; execution stops and the AI must produce a revised plan.
_Avoid_: Silent continuation, automatic recovery

**Object resolution**:
The evidence-backed process of mapping a player's name or visual description to exactly one in-scene object GUID before mutation.
_Avoid_: Name-only mutation, visual guess

**Mutation target**:
The exact object GUID returned by a current, unambiguous object-resolution result and used by a state-changing request; names, tags, and visual descriptions are discovery inputs, not mutation targets.
_Avoid_: stale GUID, direct name mutation, screenshot-only target

**Scene epoch**:
The bounded period in which a resolved object reference and plan remain applicable; save loads, identity transitions, detected external mutations, and failed verification end the epoch for the affected work and require fresh observation.
_Avoid_: timeless GUID, stale plan reuse, assumed scene continuity

**Just-in-time state gate**:
The precondition and identity check performed immediately before each plan step; it is the authoritative defense against external changes, while event notifications are advisory evidence only.
_Avoid_: continuous-watch assumption, event-only safety, stale precheck

**Freshness metadata**:
The scene epoch, observation timestamp, and request or plan identifier attached to structured observations and mutation results so clients can correlate verification and detect stale evidence.
_Avoid_: timeless response, uncorrelated readback, hidden freshness assumptions

**Durable idempotency**:
The persisted association between a plan key and its execution record across server restarts; if commit status cannot be determined, the result is uncertain and requires fresh observation rather than automatic replay.
_Avoid_: memory-only retry safety, duplicate mutation, optimistic replay

**Explicit mutation authorization**:
The caller's direct MCP request authorizing a reversible, bounded mutation after identity and state gates pass; it does not substitute for policy approval required by destructive or broad-scene actions.
_Avoid_: inferred intent, blanket approval, authorization through observation alone

**Structured scene evidence**:
The authoritative JSON state returned by the bridge for object identity, transforms, bounds, lock state, and other exact machine-readable properties.
_Avoid_: Screenshot coordinates, inferred state

**Visibility-safe observation**:
An observation filtered by the configured TTS player identity before it reaches the MCP client, containing only state that identity is permitted to see; if permission is ambiguous, the observation is withheld. Host identity does not create a generic privileged-observer exception.
_Avoid_: raw bridge dump, host override, post-exposure redaction

**Control-plane player identity**:
The TTS player color whose visibility permissions and camera are used by the generic control plane; Blue is the default, while an explicit instruction may select another identity for the applicable session or request.
_Avoid_: silent identity changes, hard-coded privacy assumptions, cross-player leakage

**Identity transition**:
A host-authorized change of control-plane player identity at a session or plan boundary; it invalidates cached observations and pending plans and requires fresh visibility reconciliation before further mutation.
_Avoid_: mid-mutation switch, stale observation reuse, caller-only escalation

**Visual scene evidence**:
An AI camera screenshot used to recognize appearance, relationships, occupancy, and approximate layout while respecting normal visibility boundaries.
_Avoid_: Exact transform source, hidden-information bypass

**Exact-state gate**:
The requirement that current structured scene evidence identifies the target and satisfies the intended preconditions before an exact mutation or verification is accepted.
_Avoid_: Screenshot-only mutation, stale state

**Verified mutation**:
A state-changing request whose expected post-state has been read back from the live bridge, including bounded settling when TTS physics is asynchronous; an unconfirmed result is pending or uncertain, not successful.
_Avoid_: optimistic success, unbounded polling, screenshot-only verification

**Tolerance-aware verification**:
The post-state comparison rule that uses documented bounded tolerances for numeric transforms and bounds, while requiring exact equality for discrete identity and state fields; results include expected, observed, and tolerance values.
_Avoid_: raw float equality, unreported slack, unverifiable success

**Effective tolerance**:
The host-policy-bounded tolerance actually used for a verification comparison; a caller may request a stricter value, never a looser one, and the effective value is returned and audited.
_Avoid_: caller-defined safety floor, hidden slack, ambiguous verification

**MVP transform tolerance**:
The default numeric verification bounds for the MVP: 0.05 TTS world units for position and 1 degree per Euler rotation axis; callers may request stricter values but not looser ones.
_Avoid_: raw float equality, undocumented defaults, loose caller override

**Control-plane failure**:
A stable machine-readable outcome class for a rejected or unresolved operation, including ambiguous target, not visible, stale precondition, conflict, policy denial, bridge error, postcondition failure, or uncertain commit, accompanied by bounded human-readable context and audit correlation.
_Avoid_: prose-only error, silent failure, unstable ad hoc codes

**Versioned control contract**:
The stable schema version carried by every generic control-plane result and failure; changes should be additive and backward-compatible, and error codes and required fields must not change silently.
_Avoid_: unversioned drift, breaking client assumptions, undocumented fields

**Capability safety metadata**:
The machine-readable contract attached to each generic tool describing whether it reads or mutates, its identity and visibility scope, target requirements, approval policy, plan eligibility, verification behavior, and failure classes.
_Avoid_: hidden safety rules, prose-only discoverability, undocumented mutation

**Capability registry**:
The single authoritative definition of generic action names, argument schemas, safety metadata, and verification expectations from which Python, Lua, and documentation compatibility are tested.
_Avoid_: duplicated inventories, bridge drift, undocumented action semantics

**Control-plane MVP slice**:
The smallest end-to-end capability proving visibility-safe observation, unique object resolution, one bounded reversible mutation with preconditions, and verified post-state; ambiguity, hidden state, stale preconditions, and concurrent plans must fail closed.
_Avoid_: broad feature inventory, unverified demo, game-legality claim

**MVP reversible action set**:
The initial generic mutation surface: move, rotate, rename, and lock or unlock an existing visible object; container/zone placement, spawning, and destruction require later capability-specific validation.
_Avoid_: premature destructive surface, unbounded action inventory, implied game legality

**MVP structured evidence**:
The first slice's observation contract: visibility-filtered machine-readable object identity and state, without requiring camera movement, screenshots, or visual inference.
_Avoid_: screenshot dependency, visual-only identity, unbounded scene dump

**MVP core path**:
The generic structured MCP control path for visibility-safe reads and bounded reversible scene actions; chat, HTTP gateway, camera, screenshots, game rules, and administrative save capabilities are adapters or later capabilities, not MVP dependencies.
_Avoid_: adapter-first validation, game-specific acceptance criteria, broad launch scope

**Generic MVP fixture**:
A dedicated minimal TTS save with a few visible, uniquely identifiable objects and no game rules, used to validate the control plane independently of chess, checkers, or other game semantics.
_Avoid_: bundled-game dependency, ambiguous fixture, rules-driven smoke test

**Visibility-denial fixture**:
The generic MVP fixture's intentionally private or concealed object owned by another identity, which must be omitted before observation reaches the MCP client.
_Avoid_: visibility-only documentation, post-exposure redaction, privileged test bypass

**Defense-in-depth visibility gate**:
The privacy boundary in which the Lua bridge may reduce observations, but the Python control-plane gate authoritatively filters again before MCP or gateway exposure; uncertainty at either layer denies the observation.
_Avoid_: Lua-only trust, Python-only raw intake, post-model filtering

**Dual bridge validation**:
The required validation split in which a deterministic fake bridge proves control-plane policy and failure semantics, while a live TTS smoke test proves the External Editor/Lua protocol, real transforms, settling, and callbacks.
_Avoid_: fake-only confidence, live-only regression testing

**MVP implementation order**:
The agreed sequence for the generic control-plane MVP: capability registry and versioned result/error schemas; deterministic fake bridge; serialized fail-fast executor with durable idempotency; Python/Lua compatibility tests; then opt-in live-TTS fixture validation.
_Avoid_: live-first development, adapter-first scope, unverified broad implementation

**Opt-in live validation**:
The explicitly invoked test suite that requires a running TTS instance and the generic MVP fixture; it is separate from default deterministic tests and must not make ordinary CI or local validation flaky.
_Avoid_: hidden live dependency, flaky default tests, fake-only release confidence

**Announced plan**:
A player-facing summary of the intended game-level operation and affected objects, published before a validated action plan executes.
_Avoid_: Low-level call narration, hidden plan

**Plan outcome**:
The player-facing result of an announced plan: completed, stopped on an execution or state error, or paused for clarification or approval.
_Avoid_: Silent partial success, internal-only status

**Partial plan result**:
A plan outcome in which earlier steps completed before a later step failed or became invalid; the AI preserves the observed scene, reports the split outcome, and does not compensate automatically.
_Avoid_: Transactional illusion, automatic rollback

**Recovery plan**:
A new, separately validated and announced action plan designed to address a partial plan result after re-observing the live scene.
_Avoid_: Retry in place, implicit compensation

**Autonomous game action**:
An AI-initiated scene change made as part of gameplay; it requires an active ruleset and game-rule adapter to validate the intended transition.
_Avoid_: Unvalidated gameplay, generic automation

**Explicit scene task**:
A player-directed generic object operation allowed without an active ruleset, provided the target is uniquely resolved and the exact-state and safety gates pass.
_Avoid_: Autonomous game action, implied permission

**Rules validation stop**:
The uncertainty stop reached when the active ruleset or adapter cannot validate the intended transition; the AI may explain the ambiguity and propose alternatives, but only the rules layer or an explicit player clarification may unblock execution.
_Avoid_: Model-only legality, best-effort move

**Validated action plan**:
The structured output of a game-rule adapter containing the intended operation, uniquely resolved object GUIDs, ordered allowlisted actions, preconditions, postconditions, and required approval class.
_Avoid_: Prose-only move, model-authored legality

**Save-file edit**:
A host-directed, validated change to the JSON representation of a TTS save on disk, performed separately from a live-scene action.
_Avoid_: Silent overwrite, live-scene mutation, arbitrary file write

**Loaded save**:
The TTS scene currently instantiated from a save through TTS's Save & Load flow; changing a save file on disk does not change the loaded scene until TTS loads it.
_Avoid_: Edited save file, stale live scene

**Save-load handoff**:
The verified result of editing and backing up a numbered save file, together with the exact path and explicit next step required to load it in TTS.
_Avoid_: Assumed reload, unverified scene state

**Administrative save capability**:
A separately enabled host-directed capability for editing a save representation or loading a saved scene; it is outside the live safe TTS control plane and follows its own backup, approval, GUI, and verification rules.
_Avoid_: ordinary live-object action, implicit whole-scene replacement

**Player intent**:
The requested outcome expressed by a player or inferred from an eligible game interaction; it is input to planning, not authority to bypass rules or safety gates.
_Avoid_: Validated action plan, implicit permission

**Plan authority**:
The game-rule adapter's responsibility to author or validate the final action plan for an autonomous game action before execution.
_Avoid_: AI-only legality, bridge-only authority

**Control-plane audit trail**:
Durable metadata for generic control-plane requests, plan and precondition results, post-state verification, policy denials, approvals, identity transitions, and bridge errors; hidden scene contents, private chat, and raw screenshots are excluded by default.
_Avoid_: payload archive, unaudited mutation, silent privacy leak

**Audit retention**:
Local control-plane audit records remain until an explicit host-controlled cleanup; the system does not silently expire safety evidence.
_Avoid_: automatic evidence deletion, remote archival by default, unbounded hidden storage
