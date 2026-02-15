import flet as ft
import cshogi

CELL = 44

# 超簡易：駒ID→文字。まずは「空/それ以外」を見分けられればOK。
# ここは後でcshogiの駒定数(BPawn等)に合わせてちゃんと作ります。 [web:86]
# 種類だけ（先手/後手で同じ表記にする）
PIECE_NAMES_14 = [
    "歩", "香", "桂", "銀", "角", "飛", "金", "玉",
    "と", "杏", "圭", "全", "馬", "龍",
]

def build_piece_text_map():
    m = {0: ""}

    black_ids = [
        cshogi.BPAWN, cshogi.BLANCE, cshogi.BKNIGHT, cshogi.BSILVER,
        cshogi.BBISHOP, cshogi.BROOK, cshogi.BGOLD, cshogi.BKING,
        cshogi.BPROM_PAWN, cshogi.BPROM_LANCE, cshogi.BPROM_KNIGHT, cshogi.BPROM_SILVER,
        cshogi.BPROM_BISHOP, cshogi.BPROM_ROOK,
    ]
    white_ids = [
        cshogi.WPAWN, cshogi.WLANCE, cshogi.WKNIGHT, cshogi.WSILVER,
        cshogi.WBISHOP, cshogi.WROOK, cshogi.WGOLD, cshogi.WKING,
        cshogi.WPROM_PAWN, cshogi.WPROM_LANCE, cshogi.WPROM_KNIGHT, cshogi.WPROM_SILVER,
        cshogi.WPROM_BISHOP, cshogi.WPROM_ROOK,
    ]

    for pid, name in zip(black_ids, PIECE_NAMES_14):
        m[pid] = name
    for pid, name in zip(white_ids, PIECE_NAMES_14):
        m[pid] = name

    return m

PIECE_TEXT = build_piece_text_map()

def piece_to_text(pid: int) -> str:
    return PIECE_TEXT.get(pid, "?")

def main(page: ft.Page):
    page.title = "Flet Shogi (moves visible)"
    board = cshogi.Board()

    selected_sq: int | None = None
    legal_to: set[int] = set()

    def rc_to_sq(r: int, c: int) -> int:
        return r * 9 + c

    def sq_to_rc(sq: int) -> tuple[int, int]:
        return divmod(sq, 9)

    cells: list[list[ft.Container]] = [[None] * 9 for _ in range(9)]

    def refresh():
        pieces81 = board.pieces  # 81マスの駒配列 [web:86]
        for sq in range(81):
            r, c = sq_to_rc(sq)
            cell = cells[r][c]
            

            pid = pieces81[sq]
            cell.content.value = piece_to_text(pid)

            if sq == selected_sq:
                cell.bgcolor = ft.Colors.BLUE_100
            elif sq in legal_to:
                cell.bgcolor = ft.Colors.GREEN_100
            else:
                cell.bgcolor = ft.Colors.AMBER_50
        page.update()

    def recompute_legal_to(frm_sq: int):
        tos = set()
        for m in board.legal_moves:  # 合法手 [web:56]
            if cshogi.move_from(m) == frm_sq:  # from抽出 [page:2]
                tos.add(cshogi.move_to(m))     # to抽出 [page:2]
        return tos

    def find_legal_move(frm_sq: int, to_sq: int):
        for m in board.legal_moves:  # 合法手から選ぶ [web:56]
            if cshogi.move_from(m) == frm_sq and cshogi.move_to(m) == to_sq:  # [page:2]
                return m
        return None

    def on_cell_click(e: ft.ControlEvent):
        nonlocal selected_sq, legal_to

        sq = int(e.control.data)

        if selected_sq is None:
            selected_sq = sq
            legal_to = recompute_legal_to(selected_sq)
            if not legal_to:
                selected_sq = None
            refresh()
            return

        if sq == selected_sq:
            selected_sq = None
            legal_to = set()
            refresh()
            return

        m = find_legal_move(selected_sq, sq)
        if m is not None:
            board.push(m)  # legal_movesから選んだ手だけ適用 [page:2]
            selected_sq = None
            legal_to = set()
            refresh()
            return

        selected_sq = sq
        legal_to = recompute_legal_to(selected_sq)
        if not legal_to:
            selected_sq = None
        refresh()

    grid_rows = []
    for r in range(9):
        row = []
        for c in range(9):
            sq = rc_to_sq(r, c)
            cell = ft.Container(
                width=CELL,
                height=CELL,
                bgcolor=ft.Colors.AMBER_50,
                border=ft.border.all(1, ft.Colors.BLACK12),
                alignment=ft.Alignment.CENTER,
                content=ft.Text("", size=16),
                data=str(sq),
                on_click=on_cell_click,
            )
            cells[r][c] = cell
            row.append(cell)
        grid_rows.append(ft.Row(row, spacing=0))

    page.add(ft.Column(grid_rows, spacing=0))
    refresh()

ft.app(target=main)
