from __future__ import annotations

import flet as ft

from shogi.board_model import BoardModel
from shogi.game_tree import GameTree
from engine.usi import UsiEngine, EngineConfig
from analysis.analyzer import Analyzer, ReviewItem


class AppState:
    def __init__(self):
        self.model = BoardModel()  # startpos
        self.tree = GameTree(self.model.sfen())
        self.engine: UsiEngine | None = None
        self.engine_cfg = EngineConfig(
            engine_path="",
            movetime_ms=2000,
            threads=4,
            hash_mb=512,
        )
        self.analyzer = Analyzer()
        self.reviews: list[ReviewItem] = []

        self.flip = False
        self.selected_sq: int | None = None
        self.legal_tos: set[int] = set()

    def reset_startpos(self):
        self.model.reset_startpos()
        self.tree = GameTree(self.model.sfen())
        self.selected_sq = None
        self.legal_tos.clear()
        self.reviews = []


def main(page: ft.Page):
    page.title = "shogi-booster"
    page.window_width = 1100
    page.window_height = 800
    page.theme_mode = ft.ThemeMode.DARK

    st = AppState()

    sfen_field = ft.TextField(label="SFEN", value=st.model.sfen(), expand=True)

    engine_path = ft.TextField(label="Engine path (例: C:/YO.exe)", expand=True)
    engine_status = ft.Text("Engine: 未接続")

    eval_text = ft.Text("評価値: --")

    move_list = ft.ListView(expand=True, spacing=2, auto_scroll=True)
    reviews_list = ft.ListView(expand=True, spacing=6)

    def ui_sq_index(ui_r: int, ui_c: int) -> int:
        # ui_r, ui_c: 0..8 (top-left origin)
        # BoardModel uses square 0..80, with (file 9..1, rank a..i) mapping hidden.
        # We'll map via BoardModel helpers that accept ui coords.
        return st.model.ui_to_sq(ui_r, ui_c, flipped=st.flip)

    def sq_to_ui(sq: int) -> tuple[int, int]:
        return st.model.sq_to_ui(sq, flipped=st.flip)

    def refresh_move_list():
        move_list.controls.clear()
        path = st.tree.current_path_moves()
        for i, mv in enumerate(path, start=1):
            move_list.controls.append(ft.Text(f"{i}. {mv}"))

    def refresh_reviews_list():
        reviews_list.controls.clear()
        if not st.reviews:
            reviews_list.controls.append(ft.Text("復習局面はまだありません"))
            return
        for item in st.reviews:
            title = f"手数 {item.ply}: Δ{item.delta_cp:+}cp / best {item.bestmove_usi}"
            btn = ft.ElevatedButton(
                text=title,
                on_click=lambda e, sfen=item.sfen_before: load_sfen(sfen),
            )
            reviews_list.controls.append(btn)

    def refresh_board():
        sfen_field.value = st.model.sfen()
        hand_b, hand_w = st.model.hands_text()
        hands_row.controls[0].value = f"先手持ち駒: {hand_b}"
        hands_row.controls[1].value = f"後手持ち駒: {hand_w}"
        turn_text.value = f"手番: {'先手' if st.model.turn_is_black() else '後手'}"

        # update squares
        for r in range(9):
            for c in range(9):
                sq = ui_sq_index(r, c)
                txt = st.model.piece_text(sq)
                b = board_buttons[r * 9 + c]
                b.text = txt

                # color
                is_sel = st.selected_sq == sq
                is_to = sq in st.legal_tos
                if is_sel:
                    b.bgcolor = ft.Colors.BLUE_700
                elif is_to:
                    b.bgcolor = ft.Colors.GREEN_700
                else:
                    b.bgcolor = ft.Colors.BLUE_GREY_900

        page.update()

    def clear_selection():
        st.selected_sq = None
        st.legal_tos.clear()

    async def ensure_engine() -> bool:
        if st.engine is not None and st.engine.is_alive():
            return True
        path = engine_path.value.strip()
        if not path:
            engine_status.value = "Engine: path未設定"
            page.update()
            return False
        st.engine_cfg.engine_path = path
        try:
            st.engine = UsiEngine(st.engine_cfg)
            await st.engine.start_async()
            engine_status.value = "Engine: 接続OK"
            page.update()
            return True
        except Exception as ex:
            engine_status.value = f"Engine: 接続失敗 ({ex})"
            st.engine = None
            page.update()
            return False

    def load_sfen(sfen: str):
        clear_selection()
        st.model.set_sfen(sfen)
        # reset tree root to this position (editing entry)
        st.tree = GameTree(st.model.sfen())
        st.reviews = []
        refresh_move_list()
        refresh_reviews_list()
        refresh_board()

    def on_set_sfen(e):
        load_sfen(sfen_field.value.strip())

    def on_flip(e):
        st.flip = not st.flip
        refresh_board()

    async def analyze_line(e):
        ok = await ensure_engine()
        if not ok:
            return
        eval_text.value = "評価値: 解析中..."
        page.update()

        # analyze along current line (root -> current)
        line = st.tree.current_line_nodes()
        st.reviews = []
        await st.analyzer.analyze_line_async(st.engine, line, movetime_ms=st.engine_cfg.movetime_ms)
        st.reviews = st.analyzer.collect_reviews(line, blunder_threshold_cp=600)
        refresh_reviews_list()
        eval_text.value = "評価値: 解析完了"
        page.update()

    async def show_current_eval(e=None):
        ok = await ensure_engine()
        if not ok:
            return
        sfen = st.model.sfen()
        info = await st.engine.analyze_position_async(sfen, movetime_ms=st.engine_cfg.movetime_ms)
        eval_text.value = f"評価値: {info.score_text()}"
        page.update()

    async def start_training_from_current(e):
        ok = await ensure_engine()
        if not ok:
            return
        training_status.value = "対局: 開始"
        training_state["active"] = True
        training_state["start_sfen"] = st.model.sfen()
        page.update()
        await show_current_eval()

    async def stop_training(e):
        training_state["active"] = False
        training_status.value = "対局: 停止"
        page.update()

    async def engine_reply_if_needed():
        if not training_state["active"]:
            return
        # engine plays the side to move? In training we want engine as opponent of the user.
        # We'll define "user" as the side to move at training start.
        user_is_black = training_state["user_is_black"]
        if st.model.turn_is_black() == user_is_black:
            return
        ok = await ensure_engine()
        if not ok:
            return
        sfen = st.model.sfen()
        bm = await st.engine.bestmove_async(sfen, movetime_ms=st.engine_cfg.movetime_ms)
        if bm.bestmove_usi and bm.bestmove_usi != "resign":
            st.model.push_usi(bm.bestmove_usi)
            st.tree.play_move_from_current(bm.bestmove_usi, st.model.sfen())
            refresh_move_list()
            refresh_board()
            await show_current_eval()

    async def on_square_click(e):
        idx = int(e.control.data)
        r, c = divmod(idx, 9)
        sq = ui_sq_index(r, c)

        # Training mode: user inputs moves, engine replies automatically.
        # Normal mode: record move in tree too.

        if st.selected_sq is None:
            # select
            if not st.model.has_piece(sq):
                return
            # in training, user can only move their side
            if training_state["active"]:
                if st.model.turn_is_black() != training_state["user_is_black"]:
                    return

            st.selected_sq = sq
            st.legal_tos = set(st.model.legal_dests_from(sq))
            refresh_board()
            return

        # second click: try move
        from_sq = st.selected_sq
        to_sq = sq

        usis = st.model.legal_usi_moves_from_to(from_sq, to_sq)
        if not usis:
            clear_selection()
            refresh_board()
            return

        if len(usis) == 1:
            chosen = usis[0]
        else:
            # promotion choice
            chosen = await pick_promotion_dialog(page, usis)
            if chosen is None:
                return

        st.model.push_usi(chosen)
        st.tree.play_move_from_current(chosen, st.model.sfen())
        clear_selection()
        refresh_move_list()
        refresh_board()
        await show_current_eval()
        await engine_reply_if_needed()

    def on_reset(e):
        st.reset_startpos()
        refresh_move_list()
        refresh_reviews_list()
        refresh_board()

    async def on_connect_engine(e):
        await ensure_engine()

    async def on_training_ready(e):
        # define user side as side-to-move at start
        training_state["user_is_black"] = st.model.turn_is_black()
        await start_training_from_current(e)

    # Board
    board_buttons: list[ft.ElevatedButton] = []
    for i in range(81):
        b = ft.ElevatedButton(
            text="",
            data=str(i),
            on_click=lambda e: page.run_task(on_square_click(e)),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=0),
                padding=0,
            ),
            height=56,
            width=56,
        )
        board_buttons.append(b)

    board_grid = ft.GridView(
        expand=False,
        runs_count=9,
        max_extent=56,
        spacing=2,
        run_spacing=2,
        controls=board_buttons,
    )

    hands_row = ft.Row(
        [ft.Text("先手持ち駒: -"), ft.Text("後手持ち駒: -")],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )
    turn_text = ft.Text("手番: --")

    # Tabs
    board_tab = ft.Column(
        [
            ft.Row(
                [
                    ft.ElevatedButton("初期局面", on_click=on_reset),
                    ft.ElevatedButton("反転", on_click=on_flip),
                    ft.ElevatedButton("現在評価", on_click=lambda e: page.run_task(show_current_eval())),
                ]
            ),
            ft.Row([turn_text, eval_text]),
            hands_row,
            board_grid,
            ft.Row([sfen_field, ft.ElevatedButton("SFENを適用", on_click=on_set_sfen)]),
        ],
        scroll=ft.ScrollMode.AUTO,
    )

    # Analysis tab
    analysis_tab = ft.Column(
        [
            ft.Row(
                [
                    engine_path,
                    ft.ElevatedButton("エンジン接続", on_click=lambda e: page.run_task(on_connect_engine(e))),
                    engine_status,
                ]
            ),
            ft.Row(
                [
                    ft.ElevatedButton("解析(現在の手順)", on_click=lambda e: page.run_task(analyze_line(e))),
                ]
            ),
            ft.Row(
                [
                    ft.Container(ft.Column([ft.Text("棋譜(現在ライン)"), move_list], expand=True), expand=True),
                    ft.Container(ft.Column([ft.Text("復習候補(クリックでその局面へ)"), reviews_list], expand=True), expand=True),
                ],
                expand=True,
            ),
        ],
        expand=True,
    )

    # Review tab (simple next-move puzzle)
    puzzle_status = ft.Text("問題: -")
    puzzle_answer = ft.Text("解答: -")

    puzzle_state = {"active": False, "sfen": None, "bestmove": None}

    async def start_puzzle(e):
        if not st.reviews:
            puzzle_status.value = "問題: 復習候補がありません"
            page.update()
            return
        # take first for now
        item = st.reviews[0]
        puzzle_state["active"] = True
        puzzle_state["sfen"] = item.sfen_before
        puzzle_state["bestmove"] = item.bestmove_usi
        st.model.set_sfen(item.sfen_before)
        st.tree = GameTree(st.model.sfen())
        clear_selection()
        puzzle_status.value = f"問題: 手数 {item.ply} の局面。次の一手を指してください"
        puzzle_answer.value = "解答: (未表示)"
        refresh_move_list()
        refresh_board()
        page.update()

    def reveal_answer(e):
        if not puzzle_state["active"]:
            return
        puzzle_answer.value = f"解答: {puzzle_state['bestmove']}"
        page.update()

    review_tab = ft.Column(
        [
            ft.Row(
                [
                    ft.ElevatedButton("復習問題を開始(先頭の候補)", on_click=lambda e: page.run_task(start_puzzle(e))),
                    ft.ElevatedButton("解答を見る", on_click=reveal_answer),
                ]
            ),
            puzzle_status,
            puzzle_answer,
            ft.Divider(),
            ft.Text("盤面タブと同じ操作で指し手入力できます。"),
        ],
        scroll=ft.ScrollMode.AUTO,
    )

    # Training tab
    training_status = ft.Text("対局: 停止")
    training_state = {"active": False, "start_sfen": None, "user_is_black": True}

    training_tab = ft.Column(
        [
            ft.Row(
                [
                    ft.ElevatedButton("この局面から開始(手番側が自分)", on_click=lambda e: page.run_task(on_training_ready(e))),
                    ft.ElevatedButton("停止", on_click=lambda e: page.run_task(stop_training(e))),
                    training_status,
                ]
            ),
            ft.Text("注意: 評価値のみ表示します(候補手/PVは表示しません)。"),
        ],
        scroll=ft.ScrollMode.AUTO,
    )

    tabs = ft.Tabs(
        selected_index=0,
        tabs=[
            ft.Tab(text="盤面", content=board_tab),
            ft.Tab(text="解析", content=analysis_tab),
            ft.Tab(text="復習", content=review_tab),
            ft.Tab(text="優勢維持", content=training_tab),
        ],
        expand=True,
    )

    page.add(tabs)

    refresh_move_list()
    refresh_reviews_list()
    refresh_board()


async def pick_promotion_dialog(page: ft.Page, usi_moves: list[str]) -> str | None:
    # usi_moves contains two moves like 7g7f and 7g7f+ (or similar)
    chosen = {"v": None}

    def choose(v: str):
        chosen["v"] = v
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("成りますか？"),
        content=ft.Text("成り/不成を選択"),
        actions=[
            ft.TextButton("不成", on_click=lambda e: choose([m for m in usi_moves if not m.endswith("+")][0])),
            ft.TextButton("成", on_click=lambda e: choose([m for m in usi_moves if m.endswith("+")][0])),
        ],
    )

    page.open(dlg)

    # wait until chosen
    while chosen["v"] is None and dlg.open:
        await page.sleep_async(0.05)

    return chosen["v"]


if __name__ == "__main__":
    ft.app(target=main)
