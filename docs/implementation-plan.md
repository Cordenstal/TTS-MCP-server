# Generic control-plane MVP implementation plan

The selected product is a safe MCP control plane for inspecting and
manipulating live Tabletop Simulator scenes through explicit requests. The
first vertical slice is game-neutral and does not depend on chess, chat,
screenshots, save editing, or autonomous game play.

1. Define the capability registry, versioned result schemas, and stable
   machine-readable failure classes.
2. Build a deterministic fake bridge that exercises identity, visibility,
   exact-GUID resolution, scene epochs, policy gates, and post-state checks.
3. Implement the serialized, fail-fast scene executor with 20-step/60-second
   budgets, just-in-time preconditions, tolerance-aware verification, and
   durable idempotency.
4. Keep the MVP mutation surface to move, rotate, rename, and lock/unlock of
   existing visible objects.
5. Add Python/Lua capability compatibility tests and audit correlation checks.
6. Create a dedicated game-neutral TTS fixture with visible objects and one
   object hidden from the configured identity.
7. Add opt-in live-TTS smoke tests covering the External Editor protocol,
   visibility filtering, real transforms, settling, and failure recovery.
8. Update the API reference, README inventory, roadmap, and live validation
   notes as the contracts stabilize.

Later capabilities—container/zone operations, spawning and destruction,
camera/screenshots, chat/HTTP adapters, game rules, and administrative save
operations—must each receive separate policy and validation slices.

Cross-cutting constraints:

- Blue is the default control-plane identity; host-only identity changes take
  effect only at a plan or session boundary and invalidate pending work.
- Visibility is filtered before MCP or gateway exposure, with deny-on-
  uncertainty and no generic host-only observer override.
- Mutations require an exact current GUID, explicit intent, current
  preconditions, and verified post-state.
- Plans are scene-only, exclusive, fail-fast, and rejected when another plan
  is active; they are never silently queued or rolled back.
- Bridge disconnects and unknown commit status produce `uncertain_commit` and
  enter read-only recovery; mutations are never retried automatically.
- The generic surface exposes no arbitrary Lua execution.
