# Standard American/English checkers ruleset

## Scope and conventions

This is the standard American/English checkers (draughts) ruleset. It is an
8×8 game played on the 32 dark squares. If the loaded table uses a different
variant, stop and ask the host to identify the variant before acting.

- Two sides play: Red and Black.
- Black moves first; turns alternate after each completed move.
- A player wins by capturing all opposing pieces or leaving the opponent with
  no legal move.
- The AI's side must be stated by the table or host. Do not infer that TTS
  Player 2/Blue is Red or Black from camera position alone.

## Setup and board coordinates

### Active TTS save mapping (host-confirmed)

- The red pieces are on the negative world-Z side of this board.
- The AI controls the non-red checkers and advances toward the red side:
  every ordinary AI man move must reduce its world `z` coordinate while also
  changing `x` diagonally. A move with unchanged or increased `z` is sideways
  or backward and is illegal for the AI's uncrowned pieces.
- A king is represented by two Checker objects vertically stacked on the same
  square. When an uncrowned black checker reaches the red-side back rank, the
  gateway clones it as the upper marker and verifies that stack. A detected
  double-stacked king may move or capture diagonally in either direction.
- Captures are still governed by the standard rules below: an uncrowned man
  may capture forward or backward when a verified capture is available.
- Use the live source piece's GUID and destination square tag. Do not infer
  forward from the camera view. Never issue `MOVE` merely to reposition
  sideways.

- Each side begins with 12 pieces on the dark squares of the three ranks
  nearest that side.
- The two middle ranks begin empty.
- Every move is diagonal and stays on dark squares.
- The table must expose a stable square-to-coordinate mapping and board
  orientation before the AI acts.
- A piece occupies at most one square. A move destination must be empty.

The AI must first identify the current side to move, all occupied dark
squares, and whether any capture is available anywhere for that side.

## Turn state machine

1. Determine the side to move from the visible turn indicator or an explicit
   host statement.
2. Re-observe all visible pieces and resolve their square locations by GUID,
   tags, and the verified board mapping.
3. Enumerate every capture for the side to move. If at least one capture
   exists, ordinary non-capturing moves are illegal.
4. If no capture exists, enumerate legal diagonal moves for the selected side.
5. Announce the intended move or complete capture sequence publicly as Blue.
6. Execute each landing and captured-piece removal through TTS actions.
7. Verify the final square, piece identity, captured-piece location, crown
   status, and next side to move.
8. If the move ended the game, announce the result. Otherwise end the turn
   and wait for the opponent's move.

## Autonomous TTS execution

When the AI controller is running and the AI's side, piece GUID, and legal
destination are verified from the current live scene inventory and camera
image, execute the move itself with `tts_move_checkers_piece`, passing the
piece GUID and the destination's `target_zone_tag`, such as `C5`. The tagged
invisible `LayoutZone` is authoritative; do not calculate or supply world X/Z
coordinates when a tagged square exists. The tool validates the diagonal,
occupancy, capture, direction, source height, and settled final transform.
If the board mapping or any mandatory capture is ambiguous, stop and ask the
host rather than guessing.

If side to move, board orientation, piece identity, square occupancy, or the
availability of a capture is ambiguous, stop and ask for clarification.
Never make a non-capturing move while a capture may exist.

If TTS physics leaves an object between squares, moving, stacked incorrectly,
or otherwise inconsistent with the announced move, treat the action as an
execution error. Report it and ask whether to retry; do not retry
automatically.

## Ordinary movement

- An uncrowned man moves one step diagonally forward onto an empty dark square.
- A man captures by jumping diagonally over one adjacent opposing piece onto
  the empty dark square immediately beyond it. In this ruleset, a man may
  capture forward or backward.
- A king moves one step diagonally in any direction onto an empty dark square.
- A king captures by jumping diagonally over one adjacent opposing piece onto
  the empty dark square immediately beyond it, in any diagonal direction.
- Pieces may not jump over friendly pieces, empty squares, or more than one
  opposing piece in a single jump.

## Mandatory captures and multiple jumps

- If any capture is available for the side to move, a capture must be made.
- A capture sequence must continue with the same piece whenever another legal
  capture is available from its new square.
- The player may choose among legal capture branches, but may not stop early
  while the same piece has another available capture.
- A captured piece is removed after each jump for purposes of the continuing
  sequence. It must not be jumped again.
- A multi-jump is one turn, even though it has multiple landing positions.
- The AI must announce the complete intended sequence when it can determine
  it; if a branch becomes ambiguous after an intermediate jump, pause and
  ask the host before continuing.

## Crowning

- A man reaching the opponent's back rank is crowned a king immediately after
  completing the move.
- In American/English checkers, if a man reaches the king row during a capture
  sequence, the turn ends immediately; it does not continue capturing as a
  king.
- A crowned king retains its color and piece identity and may move or capture
  in either diagonal direction on later turns.
- Do not replace or spawn a piece merely to represent a crown unless the table
  has no supported crown mechanism. If a replacement is required, request host
  approval and identify the source piece and destination square.

## Game end and draws

- A player wins when the opponent has no pieces remaining.
- A player also wins when the opponent has pieces remaining but no legal move.
- A player who has no legal move loses; do not confuse this with a draw.
- A draw may be declared by agreement or by the applicable table's official
  repetition/no-progress rule. The table must state which draw convention it
  enforces if this matters to play.
- A draw offer alone does not end the game. Require a clear acceptance or host
  decision.
- Treat a clear resignation in ordinary chat as a resignation only when the
  speaker's intent is unambiguous; do not infer resignation from frustration,
  silence, or an ambiguous message.

## Visibility and fairness

The AI may inspect only the visible board state available to its assigned TTS
side. It must not inspect hidden areas, private notes, concealed pieces, or
host-only state. If the save exposes private information or the camera does
not show a required square, ask the players how to proceed.

## TTS save-specific mapping

The save should provide, or allow the AI to verify, all of the following:

- Board object name/tag, orientation, and mapping from dark squares to world
  coordinates.
- One invisible locked `LayoutZone` for each board square, tagged `A1` through
  `H8`; these tags are the canonical movement destinations. Optional metadata
  tags such as `checkers-square a1` may also be present.
- Piece names such as `Red Man`, `Black Man`, `Red King`, and `Black King`.
- Piece tags such as `checkers-piece red man`,
  `checkers-piece black man`, `checkers-piece red king`, and
  `checkers-piece black king`.
- A reliable turn indicator or explicit host-managed turn state.
- The side controlled by TTS Player 2/Blue.
- The table's representation of captures, removed pieces, and crowned kings.

Tags are canonical and case-insensitive; names are display/fallback metadata.
GUIDs may be resolved dynamically, but they must not be used as a substitute
for a verified piece color, rank, or square mapping. If required tags are
missing, duplicated, contradictory, malformed, or unknown, stop before
acting and ask the host to repair the table mapping.

Captures should move the opposing piece to a visible, designated capture area
or use the table's established removal convention. Do not destroy captured
objects automatically. Any irreversible scene change or replacement piece
requires the normal host approval process.

For the bundled tagged board, captured red checkers are placed in orderly
slots beyond the board's positive-X edge (and captured black checkers beyond
the negative-X edge). This keeps them visible and recoverable while leaving
the eight-by-eight play area clear.
