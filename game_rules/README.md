# Game rules library

This directory contains host-managed, read-only rules references for games
played through the Tabletop Simulator MCP server.

Suggested layout:

```text
game_rules/
  chess/
    README.md
    rules.md
  go/
    README.md
    rules.md
```

The player should tell the AI which game directory to use at the start of a
session with `!ai game <name>`; for example, `!ai game chess` selects
`game_rules/chess/`. Rules should describe setup, turn order, legal actions, win
conditions, hidden information, and any conventions specific to the loaded
TTS table.

For autonomous play, the context should also describe turn-state transitions,
what to re-observe at each transition, and what conditions require replanning
or clarification.

If the requested game folder is missing, the AI should report that it could
not find the rules and ask the player to create the appropriate folder and
ruleset before play begins.

Do not place secrets or private player information here. The AI must not edit
rules while a game is in progress.

Rules references must also avoid embedding hidden game state, opponent hands,
or other information that would let the AI cheat.
