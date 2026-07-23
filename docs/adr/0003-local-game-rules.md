# ADR-0003: Host-managed local game rules

## Status

Accepted

## Context

The core integration must support arbitrary TTS games, but autonomous play
requires the AI to know the rules and turn structure. Visual inference alone
is not a reliable source of legal moves.

## Decision

At the beginning of a session, a human player tells the AI which game is being
played and where its rules are located. Game rules are stored in a local,
host-managed `game_rules/` directory and exposed through read-only MCP tools.

The active game/ruleset is selected through an explicit host-only in-game
command, not ordinary conversation, so casual discussion cannot accidentally
change the rules governing play.

The command uses the game name to resolve a directory under `game_rules/`,
such as `!ai game chess` resolving to `game_rules/chess/`. That directory
contains the rules and any additional context needed for the game. The AI
must not switch to a different game based on ordinary chat.

After selecting a valid game, the host explicitly enables autonomous play with
`!ai start`. Selecting a new game or starting a new session must not happen
implicitly from ordinary conversation.

`!ai start` resumes the previous AI session when state is available. The
host-only `!ai start fresh` command explicitly clears prior session state and
starts from the beginning of the selected game.

If the directory cannot be found or resolved unambiguously, the AI must not
start autonomous play. It should state that it could not find the rules and
ask the player to create an appropriate `game_rules/<name>/` folder and
ruleset.

Each game may have its own subdirectory. Human-authored rules are the
authoritative instructions for the AI's reasoning, while the live TTS table is
the source of observed state. Rules files must not be modified by the AI
during play.

The initial local reader supports Markdown (`.md`) and plain-text files.
PDF extraction and retrieval-augmented generation (RAG) are planned extension
points for complex or extensive rule systems; they should preserve the same
game selection and read-only trust boundary.

The AI should retain provenance for the rules it uses and be able to cite the
relevant file, section, or page when a player requests an explanation. It
should not add citations to ordinary chat by default. Citations follow the
request channel: public requests receive public citations, while direct
requests receive private citations.

## Consequences

The server needs safe path-scoped discovery and reading tools for the rules
directory, plus a way to select the active game/ruleset. The system should
surface missing, ambiguous, or contradictory rules instead of silently
guessing. Rules can include setup, turn order, legal actions, win conditions,
visibility/privacy, and table-specific conventions.

## Open questions

- What retrieval backend will provide PDF/RAG content?
- Should each game have a manifest with a canonical entry file and version?
- Can the host override rules for a specific session?
- What should happen when the named game directory is missing or ambiguous?
