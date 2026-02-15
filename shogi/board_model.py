from __future__ import annotations

import re
from dataclasses import dataclass

import cshogi


# --- Piece display helpers ---

_JA_PIECE = {
    "P": "歩",
    "L": "香",
    "N": "桂",
    "S": "銀",
    "G": "金",
    "B": "角",
    "R": "飛",
    "K": "玉",
    "+P": "と",
    "+L": "成香",
    "+N": "成桂",
    "+S": "成銀",
    "+B": "馬",
    "+R": "龍",
}


def _square_name_from_usi(usi_sq: str) -> tuple[int, int]:
    # '7g' -> file=7, rank='g' (a=1..i=9)
    file_ = int(usi_sq[0])
    rank_ = ord(usi_sq[1]) - ord('a') + 1
    return file_, rank_


def _ui_coords_from_usi_sq(usi_sq: str) -> tuple[int, int]:
    file_, rank_ = _square_name_from_usi(usi_sq)
    # UI row 0 top (rank 1) -> rank a is top, rank i is bottom
    r = rank_ - 1
    # UI col 0 left corresponds to file 9; file 9 is left, file 1 is right
    c = 9 - file_
    return r, c


def _usi_sq_from_ui(r: int, c: int) -> str:
    file_ = 9 - c
    rank_ = r + 1
    return f"{file_}{chr(ord('a') + rank_ - 1)}"


@dataclass
class HandCounts:
    # counts for pieces in hand (P,L,N,S,G,B,R)
    P: int = 0
    L: int = 0
    N: int = 0
    S: int = 0
    G: int = 0
    B: int = 0
    R: int = 0

    def to_text(self) -> str:
        parts = []
        for k, ja in [("R", "飛"), ("B", "角"), ("G", "金"), ("S", "銀"), ("N", "桂"), ("L", "香"), ("P", "歩")]:
            v = getattr(self, k)
            if v:
                parts.append(f"{ja}{v}")
        return " ".join(parts) if parts else "-"


def parse_sfen_hands(hand_field: str) -> tuple[HandCounts, HandCounts]:
    # SFEN hand: e.g. "2Rb3P". Uppercase = black, lowercase = white.
    if hand_field == "-":
        return HandCounts(), HandCounts()

    b = HandCounts()
    w = HandCounts()

    token_re = re.compile(r"(\d+)?([PLNSGBRplnsgbr])")
    for m in token_re.finditer(hand_field):
        n = int(m.group(1)) if m.group(1) else 1
        p = m.group(2)
        target = b if p.isupper() else w
        key = p.upper()
        setattr(target, key, getattr(target, key) + n)

    return b, w


class BoardModel:
    def __init__(self):
        self.board = cshogi.Board()

    def reset_startpos(self):
        self.board.reset()

    def sfen(self) -> str:
        return self.board.sfen()

    def set_sfen(self, sfen: str):
        if hasattr(self.board, "set_sfen"):
            self.board.set_sfen(sfen)
        else:
            self.board = cshogi.Board(sfen)

    def turn_is_black(self) -> bool:
        # cshogi: BLACK=0, WHITE=1
        return int(self.board.turn) == 0

    def has_piece(self, sq: int) -> bool:
        return self.board.piece(sq) != 0

    def piece_text(self, sq: int) -> str:
        p = int(self.board.piece(sq))
        if p == 0:
            return ""

        # Try built-in symbol tables
        for attr in ["PIECE_JAPANESE_SYMBOLS", "PIECE_SYMBOLS", "PIECE_SYMBOLS_JA"]:
            if hasattr(cshogi, attr):
                arr = getattr(cshogi, attr)
                try:
                    if 0 <= p < len(arr) and arr[p]:
                        return str(arr[p])
                except Exception:
                    pass

        # Fallback: decode SFEN at that square
        # This is a bit heavy; keep it simple by returning piece id
        return str(p)

    # --- UI coordinate mapping ---

    def ui_to_sq(self, ui_r: int, ui_c: int, flipped: bool) -> int:
        if flipped:
            ui_r = 8 - ui_r
            ui_c = 8 - ui_c
        usi_sq = _usi_sq_from_ui(ui_r, ui_c)
        file_, rank_ = _square_name_from_usi(usi_sq)
        # Convert to cshogi square index
        # cshogi uses 0..80; common mapping: sq = (file-1)*9 + (rank-1) where file=1..9, rank=1..9.
        # We'll use that mapping; if your cshogi build differs, adjust here.
        return (file_ - 1) * 9 + (rank_ - 1)

    def sq_to_ui(self, sq: int, flipped: bool) -> tuple[int, int]:
        file_ = (sq // 9) + 1
        rank_ = (sq % 9) + 1
        ui_r = rank_ - 1
        ui_c = 9 - file_
        if flipped:
            ui_r = 8 - ui_r
            ui_c = 8 - ui_c
        return ui_r, ui_c

    # --- move helpers ---

    def legal_moves(self) -> list[int]:
        lm = self.board.legal_moves
        try:
            return list(lm)
        except TypeError:
            return list(lm())

    def legal_dests_from(self, from_sq: int) -> list[int]:
        tos: set[int] = set()
        for mv in self.legal_moves():
            usi = cshogi.move_to_usi(mv)
            if "*" in usi:
                # drop like P*7f
                continue
            fr_usi = usi[:2]
            to_usi = usi[2:4]
            fr = self._sq_from_usi_sq(fr_usi)
            to = self._sq_from_usi_sq(to_usi)
            if fr == from_sq:
                tos.add(to)
        return sorted(tos)

    def legal_usi_moves_from_to(self, from_sq: int, to_sq: int) -> list[str]:
        out = []
        for mv in self.legal_moves():
            usi = cshogi.move_to_usi(mv)
            if "*" in usi:
                continue
            fr = self._sq_from_usi_sq(usi[:2])
            to = self._sq_from_usi_sq(usi[2:4])
            if fr == from_sq and to == to_sq:
                out.append(usi)
        # promotion move often ends with '+'
        out.sort(key=lambda s: (0 if s.endswith("+") else 1))
        return out

    def push_usi(self, usi: str):
        mv = cshogi.usi_to_move(usi)
        self.board.push(mv)

    def hands_text(self) -> tuple[str, str]:
        # parse SFEN field
        sfen = self.sfen()
        fields = sfen.split()
        hand_field = fields[2] if len(fields) >= 3 else "-"
        b, w = parse_sfen_hands(hand_field)
        return b.to_text(), w.to_text()

    def _sq_from_usi_sq(self, usi_sq: str) -> int:
        file_, rank_ = _square_name_from_usi(usi_sq)
        return (file_ - 1) * 9 + (rank_ - 1)
