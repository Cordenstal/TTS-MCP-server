# AI Scene Manipulation Context

This context defines how the AI participates in a live Tabletop Simulator scene. It separates generic scene manipulation from the game rules that determine whether a sequence is legal.

## Language

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
A destructive or broad-scene action that requires explicit host approval before execution, such as destroying objects, spawning objects, or changing scene-wide state.
_Avoid_: Autonomous action, blanket approval

**Uncertainty stop**:
The execution boundary where the AI pauses instead of acting when object identity, legal state, turn ownership, preconditions, or the result of an action is not sufficiently certain.
_Avoid_: Best-effort guessing, automatic retry

**Action plan**:
A bounded, ordered sequence of generic object actions evaluated with per-step preconditions and postconditions.
_Avoid_: Unbounded macro, arbitrary script

**Plan invalidation**:
A change or failed verification that makes the remaining steps of an action plan unsafe or no longer applicable; execution stops and the AI must produce a revised plan.
_Avoid_: Silent continuation, automatic recovery

**Object resolution**:
The evidence-backed process of mapping a player's name or visual description to exactly one in-scene object GUID before mutation.
_Avoid_: Name-only mutation, visual guess

**Structured scene evidence**:
The authoritative JSON state returned by the bridge for object identity, transforms, bounds, lock state, and other exact machine-readable properties.
_Avoid_: Screenshot coordinates, inferred state

**Visual scene evidence**:
An AI camera screenshot used to recognize appearance, relationships, occupancy, and approximate layout while respecting normal visibility boundaries.
_Avoid_: Exact transform source, hidden-information bypass

**Exact-state gate**:
The requirement that current structured scene evidence identifies the target and satisfies the intended preconditions before an exact mutation or verification is accepted.
_Avoid_: Screenshot-only mutation, stale state

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

**Player intent**:
The requested outcome expressed by a player or inferred from an eligible game interaction; it is input to planning, not authority to bypass rules or safety gates.
_Avoid_: Validated action plan, implicit permission

**Plan authority**:
The game-rule adapter's responsibility to author or validate the final action plan for an autonomous game action before execution.
_Avoid_: AI-only legality, bridge-only authority
