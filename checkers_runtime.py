"""Physical Save 128 board adapter for the pure checkers rules module."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from checkers_engine import CheckersEngine, Color, Move, Piece, Position


@dataclass(frozen=True, slots=True)
class PhysicalChecker:
    guid: str
    square: int
    piece: Piece
    y: float
    marker_guids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObservedBoard:
    position: Position
    checkers: tuple[PhysicalChecker, ...]
    centers: dict[int, tuple[float, float]]
    physical_file_flip: bool = False

    def checker_at(self, square: int) -> PhysicalChecker:
        for checker in self.checkers:
            if checker.square == square:
                return checker
        raise KeyError(square)

    def square_tag(self, square: int) -> str:
        CheckersEngine.validate_square(square)
        row, column = divmod(square, 8)
        physical_column = 7 - column if self.physical_file_flip else column
        return f"{chr(ord('A') + physical_column)}{row + 1}"


class CheckersBoardAdapter:
    """Translate compact live TTS records into verified rules-level state."""

    _SQUARE_TAG = re.compile(r"^[A-Ha-h][1-8]$")

    @classmethod
    def from_records(
        cls,
        *,
        pieces: list[dict[str, Any]],
        squares: list[dict[str, Any]],
        tolerance: float = 0.70,
    ) -> ObservedBoard:
        centers, physical_file_flip = cls._square_centers(
            squares,
            pieces,
            tolerance=tolerance,
        )
        grouped: dict[int, list[dict[str, Any]]] = {}
        for record in pieces:
            position = record.get("position") if isinstance(record.get("position"), dict) else {}
            try:
                x, z = float(position["x"]), float(position["z"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("checker observation has no usable x/z position") from exc
            nearest_square = min(
                centers,
                key=lambda square: (centers[square][0] - x) ** 2 + (centers[square][1] - z) ** 2,
            )
            distance = (centers[nearest_square][0] - x) ** 2 + (centers[nearest_square][1] - z) ** 2
            if distance**0.5 > tolerance:
                # Save 128 keeps captured pieces in visible off-board holding
                # rows. They are deliberately excluded from the play grid.
                continue
            grouped.setdefault(nearest_square, []).append(record)

        physical: list[PhysicalChecker] = []
        position_pieces: list[tuple[int, Piece]] = []
        for square, records in grouped.items():
            if len(records) > 2:
                raise ValueError(f"more than two checkers occupy square {cls.square_tag(square)}")
            identified: list[tuple[dict[str, Any], Color, bool]] = []
            for record in records:
                identity = " ".join(
                    [
                        str(record.get("name", "")),
                        " ".join(str(tag) for tag in record.get("tags", []) or []),
                    ]
                ).lower()
                color = cls._color(identity)
                try:
                    merged_stack = float(record.get("quantity", 0)) >= 2
                except (TypeError, ValueError):
                    merged_stack = False
                identified.append((record, color, "king" in identity or merged_stack))
            if len({color for _, color, _ in identified}) != 1:
                raise ValueError(f"stack at {cls.square_tag(square)} mixes checker colors")
            record, color, explicit_king = min(
                identified,
                key=lambda item: float((item[0].get("position") or {}).get("y", 0.0)),
            )
            king = explicit_king or len(records) == 2
            piece = Piece(color, king=king)
            guid = str(record.get("guid", "")).strip()
            if not guid:
                raise ValueError(f"checker at {cls.square_tag(square)} has no GUID")
            try:
                y = float((record.get("position") or {}).get("y", 0.0))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"checker at {cls.square_tag(square)} has no usable height") from exc
            marker_guids = tuple(
                str(item[0].get("guid", "")).strip()
                for item in identified
                if item[0] is not record and str(item[0].get("guid", "")).strip()
            )
            physical.append(PhysicalChecker(guid, square, piece, y, marker_guids))
            position_pieces.append((square, piece))

        return ObservedBoard(
            Position(tuple(position_pieces), turn=Color.BLACK),
            tuple(sorted(physical, key=lambda item: item.square)),
            centers,
            physical_file_flip,
        )

    @classmethod
    def reconcile_transition(cls, previous: Position, observed: ObservedBoard) -> tuple[Position, Move]:
        """Validate one externally completed move against the rules engine."""
        for move in CheckersEngine.legal_moves(previous):
            expected = CheckersEngine.apply(previous, move)
            if expected.pieces == observed.position.pieces:
                return expected, move
        raise ValueError("observed board does not match a legal completed move")

    @classmethod
    def _square_centers(
        cls,
        squares: list[dict[str, Any]],
        pieces: list[dict[str, Any]],
        *,
        tolerance: float,
    ) -> tuple[dict[int, tuple[float, float]], bool]:
        physical_centers: dict[int, tuple[float, float]] = {}
        for record in squares:
            tag = str(record.get("tag", "")).strip().upper()
            if not cls._SQUARE_TAG.fullmatch(tag):
                continue
            position = record.get("position") if isinstance(record.get("position"), dict) else record
            try:
                x, z = float(position["x"]), float(position["z"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"square {tag} has no usable center") from exc
            file_index = ord(tag[0]) - ord("A")
            rank_index = int(tag[1]) - 1
            physical_square = rank_index * 8 + file_index
            if physical_square in physical_centers:
                raise ValueError(f"duplicate center for {tag}")
            physical_centers[physical_square] = (x, z)
        if not physical_centers:
            raise ValueError("the observation must expose checkers square centers")

        # The rules engine uses odd-parity canonical squares. Save 128's
        # physical board uses even parity, so its file axis must be mirrored
        # into that canonical orientation. Keep the physical rank axis: the
        # engine's Black movement direction is from row 7 toward row 0, which
        # matches Save 128's Black movement from ranks 8 toward rank 1.
        # Infer the physical parity from the live pieces instead of assuming
        # every save uses the same visual orientation.
        parity_scores = {0: 0, 1: 0}
        for record in pieces:
            position = record.get("position") if isinstance(record.get("position"), dict) else {}
            try:
                x, z = float(position["x"]), float(position["z"])
            except (KeyError, TypeError, ValueError):
                continue
            nearest = min(
                physical_centers,
                key=lambda square: (physical_centers[square][0] - x) ** 2
                + (physical_centers[square][1] - z) ** 2,
            )
            distance = (
                (physical_centers[nearest][0] - x) ** 2
                + (physical_centers[nearest][1] - z) ** 2
            ) ** 0.5
            if distance <= tolerance:
                row, column = divmod(nearest, 8)
                parity_scores[(row + column) % 2] += 1

        available_parities = {
            (square // 8 + square % 8) % 2 for square in physical_centers
        }
        if len(available_parities) == 1:
            playable_parity = next(iter(available_parities))
        else:
            score = max(parity_scores.values())
            if score <= 0 or sum(value == score for value in parity_scores.values()) != 1:
                raise ValueError("could not infer the physical checkers square parity")
            playable_parity = max(parity_scores, key=parity_scores.get)

        physical_file_flip = playable_parity == 0
        centers: dict[int, tuple[float, float]] = {}
        for physical_square, center in physical_centers.items():
            physical_row, physical_column = divmod(physical_square, 8)
            if (physical_row + physical_column) % 2 != playable_parity:
                continue
            canonical_column = 7 - physical_column if physical_file_flip else physical_column
            canonical_square = physical_row * 8 + canonical_column
            centers[canonical_square] = center

        expected = {square for square in range(64) if (square // 8 + square % 8) % 2 == 1}
        if set(centers) != expected:
            raise ValueError("the observation must expose exactly the 32 playable checkers squares")
        return centers, physical_file_flip

    @staticmethod
    def _color(identity: str) -> Color:
        if "black" in identity:
            return Color.BLACK
        if "red" in identity:
            return Color.RED
        raise ValueError("checker color is not identifiable from its name or tags")

    @staticmethod
    def square_tag(square: int) -> str:
        CheckersEngine.validate_square(square)
        row, column = divmod(square, 8)
        return f"{chr(ord('A') + column)}{row + 1}"

    @staticmethod
    def test_square_records() -> list[dict[str, Any]]:
        return [
            {
                "tag": f"{chr(ord('A') + column)}{row + 1}",
                "position": {"x": float(column), "z": float(row)},
            }
            for row in range(8)
            for column in range(8)
            if (row + column) % 2 == 1
        ]


class AutonomousCheckersTurn:
    """Reconcile, search, execute, and verify one complete Black turn."""

    def __init__(
        self,
        *,
        observe: Any,
        execute_landing: Any,
        load_position: Any,
        save_position: Any,
        search_depth: int = 8,
    ) -> None:
        self.observe = observe
        self.execute_landing = execute_landing
        self.load_position = load_position
        self.save_position = save_position
        self.search_depth = max(1, min(int(search_depth), 16))

    def run(self) -> dict[str, Any]:
        observed: ObservedBoard = self.observe()
        stored = self.load_position()
        if stored is None:
            current = Position(observed.position.pieces, turn=Color.BLACK)
        else:
            previous = Position.from_record(stored)
            if previous.turn is Color.RED:
                current, human_move = CheckersBoardAdapter.reconcile_transition(previous, observed)
            elif previous.pieces != observed.position.pieces:
                # A bridge verification can fail after TTS has already
                # committed Black's move (notably when a crown merges two
                # checkers into a replacement GUID). Recover only an exact,
                # unique legal completed Black move; never replay it.
                completed = [
                    (move, CheckersEngine.apply(previous, move))
                    for move in CheckersEngine.legal_moves(previous)
                ]
                matches = [
                    (move, position)
                    for move, position in completed
                    if position.pieces == observed.position.pieces
                ]
                if len(matches) != 1:
                    raise ValueError("the board changed unexpectedly while Black was expected to move")
                move, recovered = matches[0]
                self.save_position(recovered.to_record())
                return {
                    "status": "recovered",
                    "move": {
                        "path": [observed.square_tag(square) for square in move.path],
                        "captures": [observed.square_tag(square) for square in move.captures],
                    },
                    "position": recovered.to_record(),
                }
            else:
                current = previous

        if current.turn is not Color.BLACK:
            raise ValueError("the reconciled board is not ready for the Black AI turn")
        winner = CheckersEngine.winner(current)
        if winner is not None:
            self.save_position(current.to_record())
            return {"status": "game_over", "winner": winner.value}

        # Persist the reconciled pre-move position. If TTS fails during the
        # turn, the next prompt sees a mismatch and stops instead of replaying.
        self.save_position(current.to_record())
        move = CheckersEngine.choose_move(current, depth=self.search_depth)
        landing_results: list[dict[str, Any]] = []
        for landing_index, target_square in enumerate(move.path[1:], start=1):
            source_checker = observed.checker_at(move.path[landing_index - 1])
            target_x, target_z = observed.centers[target_square]
            execution = self.execute_landing(
                source_checker.guid,
                {"x": target_x, "y": source_checker.y, "z": target_z},
            )
            if isinstance(execution, dict) and execution.get("stopped"):
                raise RuntimeError("TTS stopped while executing a checkers landing")
            observed = self.observe()
            expected_prefix = CheckersEngine.apply_prefix(current, move, landing_index)
            if observed.position.pieces != expected_prefix.pieces:
                raise RuntimeError(
                    f"TTS board did not reconcile after landing {landing_index} of {len(move.path) - 1}"
                )
            landing_results.append({"landing": observed.square_tag(target_square), "execution": execution})

        expected = CheckersEngine.apply(current, move)
        if observed.position.pieces != expected.pieces:
            raise RuntimeError("final TTS board did not reconcile with the selected checkers move")
        self.save_position(expected.to_record())
        return {
            "status": "executed",
            "move": {
                "path": [observed.square_tag(square) for square in move.path],
                "captures": [observed.square_tag(square) for square in move.captures],
            },
            "landings": landing_results,
            "position": expected.to_record(),
        }
