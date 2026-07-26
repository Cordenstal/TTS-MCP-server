# ADR-0008: Hybrid game state for autonomous checkers

## Status

Accepted

## Context

Save 128 checkers is played partly through TTS scene manipulation and partly
through human physical actions. The AI needs a serious tactical opponent, but
the language model cannot be trusted as the source of legal moves. TTS alone
also cannot provide reliable rule history or tactical search state.

The Red player moves, captures, and crowns Red pieces. The Black AI moves,
captures Red pieces, and crowns Black pieces. The player explicitly prompts the
AI when Black should act. Draws are only possible by mutual agreement.

## Decision

Use a hybrid game-state architecture:

- TTS is authoritative for visible physical facts: object identity, square,
  color, rank representation, captures, and the current board arrangement.
- A deterministic checkers rules/search module is authoritative for legal move
  generation, mandatory captures, multi-jump continuation, promotion rules,
  game termination, and tactical selection.
- The AI language model is responsible for conversation and explanations. It
  may not author an executable move outside the deterministic rules/search
  module.
- Every autonomous turn starts with a fresh physical board observation. The
  previous expected position is reconciled against that observation before
  search begins.
- Every landing in a multi-jump is executed and verified before the next
  landing. A mismatch, illegal human move, ambiguous rank, missing piece, or
  failed physical verification stops the turn without retrying.
- Self-promotion is physical player responsibility. The rules adapter verifies
  the newly crowned side during the next reconciliation.

The first game-specific adapter targets American/English checkers in Save 128.
Its rules engine should expose a small deep interface: reconstruct a position,
enumerate legal move sequences, apply a sequence, evaluate terminal state, and
select a move under a bounded search budget.

## Consequences

The project gains a reusable opponent seam: future games can provide their own
position reconstruction, legal-transition, and search implementations while
retaining the generic TTS control plane and uncertainty-stop policy.

Human moves do not need background polling. The ordinary natural-language
“your move” prompt is the observation boundary, but the adapter must still validate that the observed
Red transition is legal relative to the last verified position. A restart or
missing prior position requires a fresh setup reconciliation before autonomous
play.

The first release must not claim zero physical failures. It must guarantee
fail-closed behavior: no knowingly illegal move, no silent state repair, no
automatic retry after an uncertain commit, and no continuation after a failed
verification.

## Alternatives rejected

- TTS-only legality: insufficient for serious tactical search and history.
- Model-only board state: can drift from manual TTS actions and physics.
- Automatic draw detection: conflicts with the agreed mutual-agreement rule.
