# Game rules library

This directory contains host-managed, read-only rules references for games
played through the Tabletop Simulator MCP server.

Suggested layout:

```text
game_rules/
  chess/
    README.md
    rules.md
  killteam/
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

Each subdirectory is a selectable game. Its `rules.md` is injected into the
AI opponent's turn prompt after the game is selected with `!ai game <name>`.
The AI uses that file as the rules authority and plays as a participant; it is
not a D&D Dungeon Master or a general-purpose narrator. Add the game's board
mapping, AI side, turn detection, legal-move rules, visibility limits, and
TTS-specific action mapping here.

For Kill Team, the executable rules adapter is authoritative for legality;
`rules.md` is a host-managed context/reference for the selected
`Kill Team 3.0 Quick and Easy` variant. It must document the setup contract,
turning points, phases, visibility, terrain conventions, semantic actions,
dice workflow, scoring, and uncertainty/ruling behavior without embedding
concealed opponent state.
