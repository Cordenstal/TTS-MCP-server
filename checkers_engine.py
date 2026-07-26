"""Deterministic American/English checkers rules and tactical search.

This module has no TTS dependencies.  The TTS adapter is responsible for
mapping physical objects to a :class:`Position` and for executing a selected
move.  Keeping the rules here makes the legal-transition seam reusable and
testable for other physical adapters later.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import inf
from typing import Iterable


class Color(str, Enum):
    BLACK = "black"
    RED = "red"

    @property
    def opponent(self) -> "Color":
        return Color.RED if self is Color.BLACK else Color.BLACK


@dataclass(frozen=True, slots=True)
class Piece:
    color: Color
    king: bool = False


@dataclass(frozen=True, slots=True)
class Move:
    """A complete turn, including every landing in a multi-jump."""

    path: tuple[int, ...]
    captures: tuple[int, ...] = ()

    @property
    def is_capture(self) -> bool:
        return bool(self.captures)


@dataclass(frozen=True, slots=True)
class Position:
    """Immutable rules-level board state.

    Squares use ``row * 8 + column``.  Row zero is Black's king row and row
    seven is Red's king row.  Only dark squares are valid positions.
    """

    pieces: tuple[tuple[int, Piece], ...]
    turn: Color = Color.BLACK
    ply: int = 0

    def __post_init__(self) -> None:
        normalized = tuple(sorted(self.pieces, key=lambda item: item[0]))
        if len({square for square, _ in normalized}) != len(normalized):
            raise ValueError("a checkers square cannot contain two pieces")
        for square, piece in normalized:
            CheckersEngine.validate_square(square)
            if not isinstance(piece, Piece):
                raise TypeError("position entries must contain Piece values")
        object.__setattr__(self, "pieces", normalized)
        object.__setattr__(self, "turn", Color(self.turn))

    @classmethod
    def from_ascii(cls, value: str, *, turn: Color = Color.BLACK) -> "Position":
        rows = [line.strip() for line in value.strip().splitlines() if line.strip()]
        if len(rows) != 8 or any(len(row) != 8 for row in rows):
            raise ValueError("checkers ASCII boards must contain eight rows of eight cells")
        pieces: list[tuple[int, Piece]] = []
        for row_index, row in enumerate(rows):
            for column_index, cell in enumerate(row):
                if cell == ".":
                    continue
                if cell.lower() not in {"b", "r"}:
                    raise ValueError(f"unknown checkers cell: {cell!r}")
                square = row_index * 8 + column_index
                pieces.append(
                    (
                        square,
                        Piece(
                            Color.BLACK if cell.lower() == "b" else Color.RED,
                            king=cell.isupper(),
                        ),
                    )
                )
        return cls(tuple(pieces), turn=turn)

    def piece_at(self, square: int) -> Piece:
        for candidate, piece in self.pieces:
            if candidate == square:
                return piece
        raise KeyError(square)

    def maybe_piece_at(self, square: int) -> Piece | None:
        for candidate, piece in self.pieces:
            if candidate == square:
                return piece
        return None

    def as_dict(self) -> dict[int, Piece]:
        return dict(self.pieces)

    def to_record(self) -> dict[str, object]:
        return {
            "turn": self.turn.value,
            "ply": self.ply,
            "pieces": [
                {"square": square, "color": piece.color.value, "king": piece.king}
                for square, piece in self.pieces
            ],
        }

    @classmethod
    def from_record(cls, value: dict[str, object]) -> "Position":
        raw_pieces = value.get("pieces")
        if not isinstance(raw_pieces, list):
            raise ValueError("checkers position record has no pieces list")
        pieces: list[tuple[int, Piece]] = []
        for item in raw_pieces:
            if not isinstance(item, dict):
                raise ValueError("checkers position piece record must be an object")
            pieces.append(
                (
                    int(item["square"]),
                    Piece(Color(str(item["color"])), king=bool(item.get("king", False))),
                )
            )
        return cls(
            tuple(pieces),
            turn=Color(str(value.get("turn", Color.BLACK.value))),
            ply=int(value.get("ply", 0)),
        )


class CheckersEngine:
    """Deep rules/search module with a deliberately small public interface."""

    _DIRECTIONS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
    _PIECE_VALUE = 100
    _KING_VALUE = 175
    _WIN_SCORE = 100_000

    @staticmethod
    def validate_square(square: int) -> None:
        if not isinstance(square, int) or not 0 <= square < 64:
            raise ValueError(f"invalid checkers square: {square!r}")
        row, column = divmod(square, 8)
        if (row + column) % 2 == 0:
            raise ValueError(f"square {square} is not a playable dark square")

    @classmethod
    def legal_moves(cls, position: Position) -> tuple[Move, ...]:
        board = position.as_dict()
        captures: list[Move] = []
        for square, piece in board.items():
            if piece.color is position.turn:
                captures.extend(cls._capture_sequences(board, square, piece))
        if captures:
            return tuple(sorted(captures, key=cls._move_key))

        steps: list[Move] = []
        for square, piece in board.items():
            if piece.color is not position.turn:
                continue
            row, column = divmod(square, 8)
            for row_delta, column_delta in cls._movement_directions(piece):
                target_row = row + row_delta
                target_column = column + column_delta
                target = cls._square_or_none(target_row, target_column)
                if target is not None and target not in board:
                    steps.append(Move((square, target)))
        return tuple(sorted(steps, key=cls._move_key))

    @classmethod
    def apply(cls, position: Position, move: Move) -> Position:
        legal = cls.legal_moves(position)
        if move not in legal:
            raise ValueError("move is not legal in the supplied position")

        board = position.as_dict()
        source = move.path[0]
        piece = board.pop(source)
        for index, target in enumerate(move.path[1:]):
            if move.is_capture:
                board.pop(move.captures[index])
            piece = cls._promote_if_needed(piece, target)
        board[move.path[-1]] = piece
        return Position(tuple(board.items()), turn=position.turn.opponent, ply=position.ply + 1)

    @classmethod
    def apply_prefix(cls, position: Position, move: Move, landings: int) -> Position:
        """Apply a verified prefix of a complete multi-jump for readback.

        A prefix retains the same side to move.  It exists solely for a TTS
        adapter to verify each physical landing before the complete turn is
        committed through :meth:`apply`.
        """
        if move not in cls.legal_moves(position):
            raise ValueError("move is not legal in the supplied position")
        if not 1 <= landings <= len(move.path) - 1:
            raise ValueError("landings must identify a non-empty move prefix")
        board = position.as_dict()
        piece = board.pop(move.path[0])
        for index, target in enumerate(move.path[1 : landings + 1]):
            if move.is_capture:
                board.pop(move.captures[index])
            piece = cls._promote_if_needed(piece, target)
        board[move.path[landings]] = piece
        return Position(tuple(board.items()), turn=position.turn, ply=position.ply)

    @classmethod
    def winner(cls, position: Position) -> Color | None:
        if not any(piece.color is Color.BLACK for _, piece in position.pieces):
            return Color.RED
        if not any(piece.color is Color.RED for _, piece in position.pieces):
            return Color.BLACK
        if not cls.legal_moves(position):
            return position.turn.opponent
        return None

    @classmethod
    def choose_move(cls, position: Position, *, depth: int = 8) -> Move:
        """Choose a legal move with deterministic alpha-beta search.

        ``depth`` is measured in completed turns.  The caller can impose its
        own wall-clock budget around this pure function; the result is always
        a complete legal move sequence.
        """
        legal = cls.legal_moves(position)
        if not legal:
            raise ValueError("cannot choose a move in a terminal position")
        depth = max(1, int(depth))
        maximizing = position.turn is Color.BLACK
        best_move = legal[0]
        best_score = -inf if maximizing else inf
        table: dict[tuple[Position, int], float] = {}
        for move in legal:
            score = cls._search(cls.apply(position, move), depth - 1, -inf, inf, table)
            if (maximizing and score > best_score) or (not maximizing and score < best_score):
                best_move, best_score = move, score
        return best_move

    @classmethod
    def _search(
        cls,
        position: Position,
        depth: int,
        alpha: float,
        beta: float,
        table: dict[tuple[Position, int], float],
    ) -> float:
        winner = cls.winner(position)
        if winner is Color.BLACK:
            return cls._WIN_SCORE + depth
        if winner is Color.RED:
            return -cls._WIN_SCORE - depth
        if depth <= 0:
            return cls._evaluate(position)
        key = (position, depth)
        if key in table:
            return table[key]

        legal = cls.legal_moves(position)
        maximizing = position.turn is Color.BLACK
        if maximizing:
            value = -inf
            for move in legal:
                value = max(value, cls._search(cls.apply(position, move), depth - 1, alpha, beta, table))
                alpha = max(alpha, value)
                if alpha >= beta:
                    break
        else:
            value = inf
            for move in legal:
                value = min(value, cls._search(cls.apply(position, move), depth - 1, alpha, beta, table))
                beta = min(beta, value)
                if alpha >= beta:
                    break
        table[key] = value
        return value

    @classmethod
    def _evaluate(cls, position: Position) -> float:
        score = 0.0
        mobility = len(cls.legal_moves(position))
        for square, piece in position.pieces:
            row, _ = divmod(square, 8)
            value = cls._KING_VALUE if piece.king else cls._PIECE_VALUE
            if not piece.king:
                value += (7 - row) * 3 if piece.color is Color.BLACK else row * 3
            score += value if piece.color is Color.BLACK else -value
        return score + (mobility * 0.5 if position.turn is Color.BLACK else -mobility * 0.5)

    @classmethod
    def _capture_sequences(
        cls,
        board: dict[int, Piece],
        source: int,
        piece: Piece,
        path: tuple[int, ...] = (),
        captures: tuple[int, ...] = (),
    ) -> list[Move]:
        row, column = divmod(source, 8)
        found = False
        results: list[Move] = []
        for row_delta, column_delta in cls._DIRECTIONS:
            jumped = cls._square_or_none(row + row_delta, column + column_delta)
            landing = cls._square_or_none(row + 2 * row_delta, column + 2 * column_delta)
            if jumped is None or landing is None or landing in board:
                continue
            jumped_piece = board.get(jumped)
            if jumped_piece is None or jumped_piece.color is piece.color:
                continue
            found = True
            next_board = dict(board)
            next_board.pop(source)
            next_board.pop(jumped)
            next_piece = cls._promote_if_needed(piece, landing)
            next_board[landing] = next_piece
            next_path = path + (source, landing) if not path else path + (landing,)
            next_captures = captures + (jumped,)
            if next_piece.king and not piece.king:
                results.append(Move(next_path, next_captures))
                continue
            continuations = cls._capture_sequences(
                next_board,
                landing,
                next_piece,
                next_path,
                next_captures,
            )
            results.extend(continuations or [Move(next_path, next_captures)])
        if not found:
            return []
        return results

    @classmethod
    def _promote_if_needed(cls, piece: Piece, square: int) -> Piece:
        row, _ = divmod(square, 8)
        if piece.king:
            return piece
        if piece.color is Color.BLACK and row == 0:
            return Piece(piece.color, king=True)
        if piece.color is Color.RED and row == 7:
            return Piece(piece.color, king=True)
        return piece

    @classmethod
    def _movement_directions(cls, piece: Piece) -> Iterable[tuple[int, int]]:
        if piece.king:
            return cls._DIRECTIONS
        row_delta = -1 if piece.color is Color.BLACK else 1
        return ((row_delta, -1), (row_delta, 1))

    @staticmethod
    def _square_or_none(row: int, column: int) -> int | None:
        if not (0 <= row < 8 and 0 <= column < 8) or (row + column) % 2 == 0:
            return None
        return row * 8 + column

    @staticmethod
    def _move_key(move: Move) -> tuple[tuple[int, ...], tuple[int, ...]]:
        return move.path, move.captures
