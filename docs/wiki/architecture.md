# Architecture

```text
MCP client / Codex
        |
        | stdio MCP
        v
server.py
        |
        | JSON request/response over localhost:39999/39998
        v
Tabletop Simulator
        |
        v
tts_mcp_global.lua
```

The Python process owns MCP tool schemas, validation, screenshots, persistent
session/audit storage, and the HTTP AI gateway. The Lua script owns access to
the live TTS object model and must remain an explicit allowlisted dispatcher.

## Boundaries

### Python host

- Exposes MCP tools.
- Validates paths, action plans, limits, and approval flags.
- Captures screenshots through `mss`.
- Correlates request IDs and callbacks.
- Records audit events.
- Must not pretend a screenshot is exact structured state.

### Lua bridge

- Resolves GUIDs through `getObjectFromGUID`.
- Reads and changes live TTS objects.
- Returns JSON-safe summaries.
- Defers callbacks when TTS requires a later frame.
- Must not become an arbitrary code execution channel.

### Game rules

`game_rules/` contains game-specific knowledge. Generic TTS API documentation
belongs in the wiki/API reference layer; game rules must remain separately
scoped so they do not contaminate generic tool behavior.

## Request lifecycle

```text
inspect → resolve → validate → approve if needed → execute
       → wait for TTS settle → inspect again → visually verify when useful
```

This lifecycle should be reflected in tool descriptions and action-plan
schemas. New mutation tools should return the changed object or a clear job
handle rather than only `{success: true}`.

## Protocol invariants

- Preserve `messageID`, `requestId`, `channel`, and `ok/result/error` fields.
- Do not make nested callback calls synchronously from the external-message
  handler; use the existing deferred callback pattern.
- Keep Python action names and `MCP_HANDLERS` names synchronized.
- Bound list sizes, plan sizes, screenshot dimensions, and timeouts.
- Record failures as audit events without leaking secrets or hidden state.
