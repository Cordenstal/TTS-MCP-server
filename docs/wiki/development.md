# Development workflow

## Before changing a tool

1. Read the Python tool implementation and matching Lua handler.
2. Confirm the action name, request shape, and response shape.
3. Decide whether the operation is read-only, reversible, approval-required,
   destructive, or forbidden.
4. Add or update the wiki/API contract before relying on the behavior.

## During implementation

- Keep Python and Lua action names synchronized.
- Prefer small explicit handlers over a general-purpose evaluator.
- Return structured post-state.
- Bound inputs and output sizes.
- Preserve request IDs and deferred callback behavior.
- Add pure Python tests for validation and protocol tests for bridge behavior.
- Add a live-TTS smoke test when the change touches Lua, transforms, physics,
  spawning, cameras, or screenshots.

## Required validation

```powershell
python -m compileall -q server.py action_plan.py tests
python -m unittest discover -s tests -v
```

When TTS is available:

1. Install `tts_mcp_global.lua` in the Global script for the full runtime.
2. Install `tts_killteam_setup_global.lua` in the Global script when you want the placement-only setup bridge.
3. After the server starts, type a non-empty player chat message and confirm a `tts_chat_event` appears in `.tmp/tts_mcp_trace.log`.
4. Call `tts_ping`.
5. Call `tts_get_scene_summary` and `tts_get_object` for a known GUID.
6. Move or rotate a disposable object and verify returned post-state.
7. Test a screenshot with the intended monitor rectangle.
8. Confirm a rejected destructive action and an explicitly approved one.
9. Inspect `tts_recent_events` for errors and callback timing.

## Updating the roadmap

Move an item to `[done]` only when implementation, tests, documentation, and
live validation are complete. Add a short note under the item when behavior is
surprising or a limitation remains. If priorities change, update the
implementation-order section and explain the reason in the commit or PR.
