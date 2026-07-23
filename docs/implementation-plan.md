# Initial implementation plan

The first vertical slice follows the agreed chess smoke test:

1. Add SQLite-backed persistent sessions and the audit trail.
2. Add read-only MCP tools for the host-managed rules directory.
3. Implement host-only in-game commands, confirmations, and priority queues.
4. Implement chess tag validation and dynamic object mapping.
5. Implement the autonomous chess turn loop with plans, transitions,
   uncertainty stops, and completion announcements.
6. Add smoke-test verification for the complete flow.

Cross-cutting constraints:

- Player 2/Blue is a normal player, not a privileged observer.
- Hidden, private, and concealed information must be filtered before reaching
  the AI.
- Destructive/broad-scene actions require host approval through short
  alphanumeric action IDs.
- Captures are normal chess actions and move pieces off-board rather than
  destroying them.
- All AI-participant conversation and decision events are auditable.
