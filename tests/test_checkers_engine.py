import unittest

from checkers_engine import CheckersEngine, Color, Position
from checkers_runtime import AutonomousCheckersTurn, CheckersBoardAdapter


def board(text: str, turn: Color = Color.BLACK) -> Position:
    return Position.from_ascii(text, turn=turn)


def square(row: int, column: int) -> int:
    return row * 8 + column


class CheckersEngineTests(unittest.TestCase):
    def test_mandatory_capture_removes_non_capturing_moves(self) -> None:
        position = board(
        """
        ........
        ........
        .b......
        ..r.....
        ........
        ..b.....
        ........
        ........
        """
    )

        moves = CheckersEngine.legal_moves(position)

        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].path, (square(2, 1), square(4, 3)))
        self.assertEqual(moves[0].captures, (square(3, 2),))

    def test_men_can_capture_backward(self) -> None:
        position = board(
        """
        ........
        ........
        ...b....
        ....r...
        ........
        ........
        ........
        ........
        """
    )

        moves = CheckersEngine.legal_moves(position)

        self.assertEqual(moves[0].path, (square(2, 3), square(4, 5)))
        self.assertEqual(moves[0].captures, (square(3, 4),))

    def test_multi_jump_is_one_complete_move(self) -> None:
        position = board(
        """
        ........
        ........
        ...r....
        ........
        .r......
        b.......
        ........
        ........
        """
    )

        moves = CheckersEngine.legal_moves(position)

        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].path, (square(5, 0), square(3, 2), square(1, 4)))
        self.assertEqual(moves[0].captures, (square(4, 1), square(2, 3)))

        intermediate = CheckersEngine.apply_prefix(position, moves[0], 1)
        self.assertEqual(intermediate.turn, Color.BLACK)
        self.assertEqual(intermediate.piece_at(square(3, 2)).color, Color.BLACK)
        self.assertIsNone(intermediate.maybe_piece_at(square(4, 1)))

    def test_promotion_ends_a_capture_sequence_and_changes_rank(self) -> None:
        position = board(
        """
        ........
        ..r.....
        .b......
        ........
        ........
        ........
        ........
        ........
        """
    )
        move = CheckersEngine.legal_moves(position)[0]

        self.assertEqual(move.path, (square(2, 1), square(0, 3)))
        self.assertTrue(CheckersEngine.apply(position, move).piece_at(square(0, 3)).king)

    def test_game_reports_winner_when_side_to_move_has_no_legal_move(self) -> None:
        position = board(
        """
        .b......
        ........
        ........
        ........
        ........
        ........
        .......r
        ........
        """
    )

        self.assertEqual(CheckersEngine.winner(position), Color.RED)

    def test_search_returns_only_a_legal_move(self) -> None:
        position = board(
        """
        ........
        ........
        ........
        ..r.....
        .b......
        ........
        ........
        ........
        """
    )

        move = CheckersEngine.choose_move(position, depth=4)

        self.assertIn(move, CheckersEngine.legal_moves(position))

    def test_position_round_trips_for_durable_reconciliation(self) -> None:
        position = board(
            """
            ........
            ........
            ........
            ........
            ........
            ........
            .r......
            ........
            """,
            turn=Color.RED,
        )

        self.assertEqual(Position.from_record(position.to_record()), position)

    def test_live_observation_reconciles_a_human_red_move(self) -> None:
        previous = board(
            """
            ........
            r.......
            ........
            ........
            ........
            ........
            ........
            ........
            """,
            turn=Color.RED,
        )
        observed = CheckersBoardAdapter.from_records(
            pieces=[{"guid": "red-1", "name": "Red Checker", "position": {"x": 1, "y": 1, "z": 2}}],
            squares=CheckersBoardAdapter.test_square_records(),
        )

        reconciled, move = CheckersBoardAdapter.reconcile_transition(previous, observed)

        self.assertEqual(move.path, (square(1, 0), square(2, 1)))
        self.assertEqual(reconciled.turn, Color.BLACK)

    def test_live_observation_recognizes_a_merged_quantity_two_stack_as_a_king(self) -> None:
        observed = CheckersBoardAdapter.from_records(
            pieces=[{
                "guid": "merged-king",
                "name": "Black Checker",
                "quantity": 2,
                "position": {"x": 1, "y": 2, "z": 2},
            }],
            squares=CheckersBoardAdapter.test_square_records(),
        )

        self.assertEqual(len(observed.checkers), 1)
        self.assertTrue(observed.checkers[0].piece.king)

    def test_live_observation_rejects_an_illegal_human_transition(self) -> None:
        previous = board(
            """
            ........
            r.......
            ........
            ........
            ........
            ........
            ........
            ........
            """,
            turn=Color.RED,
        )
        observed = CheckersBoardAdapter.from_records(
            pieces=[{"guid": "red-1", "name": "Red Checker", "position": {"x": 4, "y": 1, "z": 2}}],
            squares=CheckersBoardAdapter.test_square_records(),
        )

        with self.assertRaisesRegex(ValueError, "does not match a legal"):
            CheckersBoardAdapter.reconcile_transition(previous, observed)

    def test_save128_starting_board_does_not_report_red_as_winner(self) -> None:
        """Save 128 uses the opposite physical checkerboard parity."""
        squares = [
            {
                "tag": f"{chr(ord('A') + column)}{row + 1}",
                "position": {"x": float(7 - column), "z": float(row)},
            }
            for row in range(8)
            for column in range(8)
        ]
        pieces = []
        for row, color in ((0, "Black"), (1, "Black"), (2, "Black"), (5, "Red"), (6, "Red"), (7, "Red")):
            for column in range(8):
                if (row + column) % 2 != 1:
                    continue
                pieces.append({
                    "guid": f"{color.lower()}-{row}-{column}",
                    "name": f"{color} Checker",
                    "position": {"x": float(7 - column), "y": 1.0, "z": float(7 - row)},
                })

        observed = CheckersBoardAdapter.from_records(pieces=pieces, squares=squares)

        self.assertEqual(len(observed.position.pieces), 24)
        self.assertIsNone(CheckersEngine.winner(observed.position))

    def test_autonomous_turn_executes_and_persists_a_verified_capture(self) -> None:
        start = board(
            """
            ........
            ........
            ........
            ........
            .r......
            b.......
            ........
            ........
            """
        )
        expected = CheckersEngine.apply(start, CheckersEngine.legal_moves(start)[0])

        def records(position: Position) -> list[dict]:
            result = []
            for item, piece in position.pieces:
                row, column = divmod(item, 8)
                result.append({
                    "guid": f"{piece.color.value}-{item}",
                    "name": f"{piece.color.value.title()} Checker",
                    "position": {"x": column, "y": 1.0, "z": row},
                })
            return result

        observations = [
            CheckersBoardAdapter.from_records(pieces=records(start), squares=CheckersBoardAdapter.test_square_records()),
            CheckersBoardAdapter.from_records(pieces=records(expected), squares=CheckersBoardAdapter.test_square_records()),
        ]
        calls: list[tuple[str, dict]] = []
        saved: list[dict] = []

        result = AutonomousCheckersTurn(
            observe=lambda: observations.pop(0),
            execute_landing=lambda guid, position: calls.append((guid, position)) or {"stopped": False},
            load_position=lambda: None,
            save_position=lambda position: saved.append(position),
            search_depth=2,
        ).run()

        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["move"]["path"], ["A6", "C4"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(saved[-1], expected.to_record())

    def test_autonomous_turn_recovers_a_completed_merged_crown_after_verification_loss(self) -> None:
        start = board(
            """
            ........
            b.......
            ........
            ........
            ........
            ..r.....
            ........
            ........
            """
        )
        move = CheckersEngine.legal_moves(start)[0]
        expected = CheckersEngine.apply(start, move)

        def records(position: Position) -> list[dict]:
            result = []
            for item, piece in position.pieces:
                row, column = divmod(item, 8)
                result.append({
                    "guid": f"{piece.color.value}-{item}",
                    "name": f"{piece.color.value.title()} Checker",
                    "quantity": 2 if piece.king else -1,
                    "position": {"x": column, "y": 2.0 if piece.king else 1.0, "z": row},
                })
            return result

        saved: list[dict] = []
        result = AutonomousCheckersTurn(
            observe=lambda: CheckersBoardAdapter.from_records(
                pieces=records(expected),
                squares=CheckersBoardAdapter.test_square_records(),
            ),
            execute_landing=lambda *_args: self.fail("a recovered move must not be replayed"),
            load_position=lambda: start.to_record(),
            save_position=lambda position: saved.append(position),
            search_depth=2,
        ).run()

        self.assertEqual(result["status"], "recovered")
        self.assertEqual(result["position"], expected.to_record())
        self.assertEqual(saved[-1], expected.to_record())
