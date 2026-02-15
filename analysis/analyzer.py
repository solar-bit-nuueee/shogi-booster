from __future__ import annotations

import asyncio
from dataclasses import dataclass

from engine.usi import UsiEngine
from shogi.game_tree import Node


@dataclass
class ReviewItem:
    ply: int
    sfen_before: str
    bestmove_usi: str
    delta_cp: int


class Analyzer:
    async def analyze_line_async(self, engine: UsiEngine, line_nodes: list[Node], movetime_ms: int = 2000):
        # line_nodes: root->...->current, each node has node.sfen AFTER its move.
        # We analyze each ply at the position before the move (parent.sfen).
        if len(line_nodes) <= 1:
            return

        # Ensure engine ready
        await engine.start_async()

        for ply, node in enumerate(line_nodes[1:], start=1):
            assert node.parent is not None
            sfen_before = node.parent.sfen
            played = node.move_usi

            best = await engine.analyze_position_async(sfen_before, movetime_ms=movetime_ms)
            node.bestmove_usi = best.bestmove_usi
            node.best_cp = best.score_cp

            # played move evaluation (searchmoves)
            if played:
                played_info = await engine.eval_searchmoves_async(
                    sfen_before, movetime_ms=max(500, movetime_ms // 2), usi_move=played
                )
                node.played_cp = played_info.score_cp

            if node.best_cp is not None and node.played_cp is not None:
                node.delta_cp = node.best_cp - node.played_cp

            # allow UI to breathe
            await asyncio.sleep(0)

    def collect_reviews(self, line_nodes: list[Node], blunder_threshold_cp: int = 600) -> list[ReviewItem]:
        out: list[ReviewItem] = []
        for ply, node in enumerate(line_nodes[1:], start=1):
            if node.delta_cp is None or node.bestmove_usi is None or node.parent is None:
                continue
            if node.delta_cp >= blunder_threshold_cp:
                out.append(
                    ReviewItem(
                        ply=ply,
                        sfen_before=node.parent.sfen,
                        bestmove_usi=node.bestmove_usi,
                        delta_cp=node.delta_cp,
                    )
                )
        return out
