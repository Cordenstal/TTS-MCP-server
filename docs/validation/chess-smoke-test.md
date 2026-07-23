# Chess smoke test

## Goal

Validate the generic AI-to-TTS flow with the initial standard chess ruleset
without requiring a complete chess game.

## Preconditions

- Tabletop Simulator is running the initially saved chess table.
- Player 2/Blue controls White.
- Chess pieces and squares use the documented names/tags.
- `game_rules/chess/rules.md` is available.
- The MCP server and SQLite session database are running.

## Scenario

1. Confirm the chess table contains valid, unique, case-insensitive piece and
   square tags.
2. Send `!ai game chess` as the host.
3. Send `!ai start` as the host.
4. Verify that the AI reports a valid active chess session.
5. Verify that the AI identifies White/Blue's turn and announces a legal move
   plan publicly.
6. Verify that the AI moves the selected piece through TTS object actions.
7. Verify that the AI announces completion of its turn.
8. Verify that SQLite contains the completed-turn checkpoint and audit events.
9. Send `!ai status` and verify it reports the active game, session state,
   current turn, and no pending error/approval.

## Expected safety behavior

- Invalid or ambiguous tags block start and list every validation failure.
- The AI never receives hidden or private information.
- No host approval is required for an ordinary non-capturing chess move.
- Any explicit TTS action error is reported and requires player guidance.
