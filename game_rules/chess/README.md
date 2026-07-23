# Chess rules/context

This directory is the initial validation ruleset for the AI player. Add the
authoritative chess rules and Tabletop Simulator table context here before
starting autonomous play with:

```text
!ai game chess
!ai start
```

The rules/context should define setup, legal moves, turn ownership, state
transitions, check/checkmate or other end conditions, draw conditions, and
what the AI may observe as Player 2/Blue.

Do not start autonomous play until the rules are populated and reviewed.
