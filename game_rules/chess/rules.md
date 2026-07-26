# Standard chess starter ruleset

## Scope

This is a starter reference for standard chess. The loaded Tabletop Simulator
save must still provide the board/object mapping and confirm how moves are
represented in the scene.

## Players and setup

- White moves first.
- Black moves second.
- The AI is Player 2/Blue and plays White in the initial validation save. The
  rules context must still state the side explicitly for each save.
- Set up an 8×8 board with each side's pieces in the standard starting
  position: king, queen, two rooks, two bishops, two knights, and eight pawns.
- The AI must not act until it can identify the board orientation, piece
  colors, and which side Blue controls.
- The initial validation save uses standard White-side orientation: White's
  back rank is nearest the Blue camera and square coordinates follow the
  conventional White perspective.

## Turn state machine

1. Determine whose turn it is.
2. Observe the permitted board state at the transition.
3. Determine whether the side to move is in check and enumerate legal moves.
4. Announce the intended plan publicly as Blue.
5. Execute the selected legal move through TTS object actions.
6. Treat a successful TTS response as execution completion unless an explicit
   error is returned.
7. At the next transition, re-observe the board and verify the resulting game
   state.
8. If the move ended the game, announce the result; otherwise announce that
   the AI's turn is complete when Blue's turn has ended.

If board state, turn ownership, or legality is unclear, stop and ask the
players for clarification. Never guess.

If TTS physics causes a moved or captured piece to drift, settle incorrectly,
or otherwise fail to match the requested square/area, treat it as an
execution error. Report the error and ask whether to retry or choose a
different action; do not retry automatically.

## Piece movement

- King: one square in any direction; it may not move into check.
- Queen: any number of unobstructed squares along a rank, file, or diagonal.
- Rook: any number of unobstructed squares along a rank or file.
- Bishop: any number of unobstructed squares along a diagonal.
- Knight: an L-shaped move: two squares in one direction and one
  perpendicular; it may jump over pieces.
- Pawn: one square forward into an empty square; from its starting rank it may
  move two squares if both squares are empty; it captures one square
  diagonally forward. Pawns cannot move backward.

A move is legal only if it does not leave the moving side's king in check.
Pieces block sliding movement. A capture removes the opposing piece from the
destination square. In the TTS save, a captured piece must be moved to the
off-board space rather than destroyed; no named capture area is required. This
is normal gameplay and does not require host approval. Keep captured pieces
neatly grouped by color so the capture state remains visually legible during
reconciliation.

## Tabletop Simulator move execution

The board has one invisible locked `LayoutZone` for every square, tagged
`A1` through `H8`. These tags are the authoritative destinations for chess
moves. Treat tags case-insensitively: `A1` means a1, `E4` means e4, and so on.

For a normal piece move, call `tts_place_in_tagged_zone` with the moving piece
GUID as `target_guid` and the destination square as `zone_tag`, for example
`zone_tag: "E4"`. Do not calculate or supply world-space X/Z coordinates for
chess moves. The tool resolves the unique tagged LayoutZone and moves the piece
to its center. Verify the returned live position before continuing.

Use the same operation for castling's king and rook as two coordinated
placements. Move captured pieces off-board as described above.

## Special moves

- Castling is permitted only if the king and involved rook have not moved,
  the squares between them are empty, the king is not currently in check, and
  the king does not cross or land on an attacked square.
- Execute castling as one announced chess action containing the coordinated
  king and rook movements; verify both placements together at the next state
  transition.
- En passant is permitted immediately after an opposing pawn moves two
  squares and lands beside the capturing pawn. The capture must be performed
  on the immediately following move or the right expires. Execute it as one
  announced action containing the pawn move and the captured pawn's off-board
  movement.
- When a pawn reaches the last rank, it must promote to a queen, rook, bishop,
  or knight. The AI announces the chosen piece in its turn plan and proceeds
  without an extra player confirmation. Use an existing off-board piece of the
selected type rather than spawning a new object. The promoted piece must be
verified at the next rules-defined transition.

If no suitable off-board piece is available, request host approval to spawn a
replacement. The proposal must identify the color and type; do not spawn it
automatically. After approval, apply the standard chess name/tag and verify
the spawned piece at the next state transition.

## Check and game end

- A king is in check when an opposing legal attack targets its square.
- Check must be answered on the next move; the king may move, the attacking
  piece may be captured, or the attack may be blocked when possible.
- Checkmate occurs when the side in check has no legal move.
- Stalemate occurs when the side not in check has no legal move.
- A player wins by checkmate or by the opponent resigning.
- A draw may occur by stalemate, agreement, insufficient mating material,
  threefold repetition, the fifty-move rule, or fivefold repetition/seventy-
  five-move rule where the applicable standard rule is enforced by the table.
- Treat clear ordinary-chat resignation statements as resignation events and
  clear ordinary-chat draw offers/acceptances as draw-agreement events. Do not
  infer either result from ambiguous conversation.
- The host has final authority over a draw decision. A draw offer alone does
  not end the game; wait for a clear host decision expressed in ordinary
  conversation.

## Visibility and fairness

The AI may inspect only the visible board state available to Blue. It must not
inspect hidden hands, concealed pieces, private notes, or any host-only state.
If the TTS save exposes private or ambiguous information, withhold it and ask
the players how to proceed.

## Save-specific context to add

- Board object's name/tag and orientation.
- Mapping from board squares to world coordinates.
- Piece object names/tags and the discovery rules used to map them to squares;
  GUIDs may be resolved dynamically at runtime.
- Use human-readable piece names such as `White King` and `Black Pawn`.
- Use piece tags such as `chess-piece white king` and
  `chess-piece black pawn`.
- Use invisible square zones tagged `A1` through `H8` as the canonical
  destinations. Optional metadata tags such as `chess-square e4` may also be
  present, but are not required when the LayoutZone tags exist.
- Treat tag matching as case-insensitive; the lowercase forms shown here are
  canonical for documentation and diagnostics.
- Treat tags as canonical and names as display/fallback metadata.
- Whether Blue controls White or Black.

If required chess tags are missing, duplicated, contradictory, malformed, or
unknown, stop before acting and ask the players to repair the table mapping.
Do not infer a piece identity or square from an ambiguous tag.

Run this mapping validation automatically when `!ai game chess` or `!ai start`
is processed; no separate validation command is required.
- How castling, en passant, promotion, capture, resignation, and turn ending
  are represented in the TTS save.
- Which object actions require host approval.
