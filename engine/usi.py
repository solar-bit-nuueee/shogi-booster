from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass


_SCORE_RE = re.compile(r"score\s+(cp|mate)\s+(-?\d+)")
_BESTMOVE_RE = re.compile(r"^bestmove\s+(\S+)")


@dataclass
class EngineConfig:
    engine_path: str
    movetime_ms: int = 2000
    threads: int = 4
    hash_mb: int = 512


@dataclass
class AnalyzeInfo:
    bestmove_usi: str | None
    score_cp: int | None
    score_mate: int | None

    def score_text(self) -> str:
        if self.score_mate is not None:
            return f"mate {self.score_mate}"
        if self.score_cp is not None:
            return f"{self.score_cp:+}cp"
        return "--"


class UsiEngine:
    def __init__(self, cfg: EngineConfig):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self._stdout_task: asyncio.Task | None = None
        self._lines: asyncio.Queue[str] = asyncio.Queue()

    def is_alive(self) -> bool:
        return self.proc is not None and (self.proc.poll() is None)

    async def start_async(self):
        if self.proc is not None:
            return
        self.proc = subprocess.Popen(
            [self.cfg.engine_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None

        self._stdout_task = asyncio.create_task(self._reader_task(self.proc.stdout))

        await self._send("usi")
        await self._wait_for("usiok", timeout=10)

        await self._setoption("Threads", str(self.cfg.threads))
        await self._setoption("Hash", str(self.cfg.hash_mb))

        await self._send("isready")
        await self._wait_for("readyok", timeout=30)

    async def quit_async(self):
        if not self.is_alive():
            return
        await self._send("quit")
        try:
            await asyncio.wait_for(self._stdout_task, timeout=1)
        except Exception:
            pass
        self.proc = None

    async def analyze_position_async(self, sfen: str, movetime_ms: int) -> AnalyzeInfo:
        await self._send(f"position sfen {sfen}")
        await self._send(f"go movetime {movetime_ms}")
        bestmove, cp, mate = await self._collect_until_bestmove(timeout=movetime_ms / 1000 + 10)
        return AnalyzeInfo(bestmove_usi=bestmove, score_cp=cp, score_mate=mate)

    async def bestmove_async(self, sfen: str, movetime_ms: int) -> AnalyzeInfo:
        return await self.analyze_position_async(sfen, movetime_ms)

    async def eval_searchmoves_async(self, sfen: str, movetime_ms: int, usi_move: str) -> AnalyzeInfo:
        # Evaluate a specific move by restricting searchmoves
        await self._send(f"position sfen {sfen}")
        await self._send(f"go movetime {movetime_ms} searchmoves {usi_move}")
        bestmove, cp, mate = await self._collect_until_bestmove(timeout=movetime_ms / 1000 + 10)
        return AnalyzeInfo(bestmove_usi=bestmove, score_cp=cp, score_mate=mate)

    async def _setoption(self, name: str, value: str):
        await self._send(f"setoption name {name} value {value}")

    async def _send(self, cmd: str):
        if not self.is_alive():
            raise RuntimeError("engine is not running")
        assert self.proc is not None
        assert self.proc.stdin is not None
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    async def _reader_task(self, stdout):
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, stdout.readline)
            if not line:
                break
            await self._lines.put(line.strip())

    async def _wait_for(self, token: str, timeout: float):
        try:
            while True:
                line = await asyncio.wait_for(self._lines.get(), timeout=timeout)
                if token in line:
                    return
        except asyncio.TimeoutError as e:
            raise TimeoutError(f"timeout waiting for {token}") from e

    async def _collect_until_bestmove(self, timeout: float) -> tuple[str | None, int | None, int | None]:
        bestmove = None
        last_cp = None
        last_mate = None

        try:
            while True:
                line = await asyncio.wait_for(self._lines.get(), timeout=timeout)

                m = _SCORE_RE.search(line)
                if m:
                    kind = m.group(1)
                    val = int(m.group(2))
                    if kind == "cp":
                        last_cp = val
                        last_mate = None
                    else:
                        last_mate = val
                        last_cp = None

                bm = _BESTMOVE_RE.match(line)
                if bm:
                    bestmove = bm.group(1)
                    break
        except asyncio.TimeoutError:
            pass

        return bestmove, last_cp, last_mate
