from __future__ import annotations

from typing import TYPE_CHECKING
import numpy as np
from loguru import logger

if TYPE_CHECKING:
    from swyft.core.piece_manager import PieceManager, PieceState
    from swyft.core.peer_manager import PeerInfo


class DownloadOptimizer:
    """
    Decides which pieces to request and in what order using a
    weighted combination of rarity-first and speed-based lookahead.

    Strategy:
      - Rarest-first for global efficiency (prevents piece starvation)
      - Speed-weighted selection per peer to maximise throughput
      - Endgame mode: broadcast last N pieces to all peers simultaneously
    """

    ENDGAME_THRESHOLD = 0.95     # switch to endgame when 95% complete

    def __init__(self, config: dict):
        cfg = config["ml"]["download_optimizer"]
        self.lookahead = cfg.get("lookahead_pieces", 20)
        self.rarity_weight = cfg.get("rarity_weight", 0.6)
        self.speed_weight = cfg.get("speed_weight", 0.4)
        self._endgame_active = False

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def get_request_queue(
        self,
        piece_manager: "PieceManager",
        peer: "PeerInfo",
        n: int = 5,
    ) -> list[int]:
        from swyft.core.piece_manager import PieceState

        progress = piece_manager.progress()
        if progress >= self.ENDGAME_THRESHOLD:
            if not self._endgame_active:
                logger.info("[Optimizer] Entering endgame mode")
                self._endgame_active = True
            return self._endgame_selection(piece_manager, n)

        return self._normal_selection(piece_manager, peer, n)

    def reset(self):
        self._endgame_active = False

    # ------------------------------------------------------------------ #
    # Piece selection strategies                                           #
    # ------------------------------------------------------------------ #

    def _normal_selection(
        self,
        piece_manager: "PieceManager",
        peer: "PeerInfo",
        n: int,
    ) -> list[int]:
        from swyft.core.piece_manager import PieceState

        if not peer.peer_id or peer.peer_id not in piece_manager._peer_bitfields:
            return self._fallback(piece_manager, n)

        peer_has = piece_manager._peer_bitfields[peer.peer_id]
        candidates = [
            i for i, p in enumerate(piece_manager.pieces)
            if p.state in (PieceState.MISSING, PieceState.FAILED) and i in peer_has
        ]

        if not candidates:
            return []

        # Score each candidate
        scores = np.array([self._score_piece(i, piece_manager, peer) for i in candidates])
        top_indices = np.argsort(-scores)[:n]
        return [candidates[i] for i in top_indices]

    def _score_piece(
        self,
        piece_idx: int,
        piece_manager: "PieceManager",
        peer: "PeerInfo",
    ) -> float:
        availability = piece_manager._availability.get(piece_idx, 1)
        rarity_score = 1.0 / max(availability, 1)

        # Penalise pieces already being downloaded by other peers
        if piece_manager.pieces[piece_idx].assigned_to is not None:
            rarity_score *= 0.5

        speed_score = min(peer.download_speed_bps / 1e6, 1.0)

        return self.rarity_weight * rarity_score + self.speed_weight * speed_score

    def _endgame_selection(self, piece_manager: "PieceManager", n: int) -> list[int]:
        from swyft.core.piece_manager import PieceState
        missing = [
            p.index for p in piece_manager.pieces
            if p.state in (PieceState.MISSING, PieceState.DOWNLOADING, PieceState.FAILED)
        ]
        return missing[:n]

    def _fallback(self, piece_manager: "PieceManager", n: int) -> list[int]:
        from swyft.core.piece_manager import PieceState
        return [
            p.index for p in piece_manager.pieces
            if p.state in (PieceState.MISSING, PieceState.FAILED)
        ][:n]

    # ------------------------------------------------------------------ #
    # Analytics helpers                                                    #
    # ------------------------------------------------------------------ #

    def estimated_completion_order(self, piece_manager: "PieceManager") -> list[int]:
        """Return all missing pieces ranked by priority (for analytics only)."""
        from swyft.core.piece_manager import PieceState
        missing = [
            p.index for p in piece_manager.pieces
            if p.state in (PieceState.MISSING, PieceState.FAILED)
        ]
        missing.sort(key=lambda i: piece_manager._availability.get(i, 0))
        return missing
