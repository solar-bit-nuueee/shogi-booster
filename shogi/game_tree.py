from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Node:
    sfen: str
    move_usi: str | None = None
    parent: "Node | None" = None
    children: list["Node"] = field(default_factory=list)

    # analysis (position BEFORE this move is stored in parent)
    bestmove_usi: str | None = None
    best_cp: int | None = None
    played_cp: int | None = None
    delta_cp: int | None = None


class GameTree:
    def __init__(self, root_sfen: str):
        self.root = Node(sfen=root_sfen)
        self.current = self.root

    def play_move_from_current(self, move_usi: str, resulting_sfen: str) -> Node:
        # If same move already exists as a child, follow it.
        for ch in self.current.children:
            if ch.move_usi == move_usi:
                self.current = ch
                return ch

        nd = Node(sfen=resulting_sfen, move_usi=move_usi, parent=self.current)
        self.current.children.append(nd)
        self.current = nd
        return nd

    def goto_root(self):
        self.current = self.root

    def goto_parent(self):
        if self.current.parent is not None:
            self.current = self.current.parent

    def current_path_nodes(self) -> list[Node]:
        # root -> current
        nodes = []
        n: Node | None = self.current
        while n is not None:
            nodes.append(n)
            n = n.parent
        return list(reversed(nodes))

    def current_path_moves(self) -> list[str]:
        nodes = self.current_path_nodes()
        return [n.move_usi for n in nodes[1:] if n.move_usi]

    def current_line_nodes(self) -> list[Node]:
        # for now: analyze the current path (root->current)
        return self.current_path_nodes()
