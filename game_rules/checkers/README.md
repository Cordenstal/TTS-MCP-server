# Checkers rules/context

This directory contains the standard American/English checkers ruleset for
the AI player. Before autonomous play, select it and start the session:

```text
!ai game checkers
!ai start
```

The rules assume an 8×8 board using only the 32 dark squares. The loaded
Tabletop Simulator save must still define the board orientation, side colors,
piece tags, square mapping, and turn indicator.

Do not start autonomous play until that save-specific mapping has been
observed and verified.
