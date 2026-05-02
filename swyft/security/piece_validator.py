from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from swyft.core.peer_manager import PeerInfo


class PieceValidator:
    """
    Validates piece integrity against the torrent's SHA-1 hash list.

    Tracks which peers supplied bad pieces to feed the reputation system.
    Detects torrent poisoning when a single piece consistently fails from
    multiple peers (suggests the .torrent file itself is corrupt/malicious).
    """

    POISON_THRESHOLD = 3   # if N+ different peers all fail the same piece

    def __init__(self, piece_hashes: list[bytes]):
        self.piece_hashes = piece_hashes
        self._fail_count: dict[int, int] = defaultdict(int)
        self._fail_peers: dict[int, set[str]] = defaultdict(set)
        self._poisoned_pieces: set[int] = set()
        self._total_validated = 0
        self._total_passed = 0

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def validate(self, piece_index: int, data: bytes, peer: "PeerInfo") -> bool:
        self._total_validated += 1
        expected = self.piece_hashes[piece_index]
        actual = hashlib.sha1(data).digest()

        if actual == expected:
            self._total_passed += 1
            return True

        self._record_failure(piece_index, peer)
        return False

    def is_poisoned(self, piece_index: int) -> bool:
        return piece_index in self._poisoned_pieces

    def get_stats(self) -> dict:
        return {
            "validated": self._total_validated,
            "passed": self._total_passed,
            "failed": self._total_validated - self._total_passed,
            "pass_rate": self._total_passed / self._total_validated if self._total_validated else 1.0,
            "poisoned_pieces": list(self._poisoned_pieces),
        }

    def bad_piece_count(self, peer: "PeerInfo") -> int:
        return sum(
            1 for peers in self._fail_peers.values()
            if peer.key in peers
        )

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _record_failure(self, piece_index: int, peer: "PeerInfo"):
        self._fail_count[piece_index] += 1
        self._fail_peers[piece_index].add(peer.key)

        logger.warning(
            f"[Validator] Piece {piece_index} failed from {peer.ip} "
            f"(total failures: {self._fail_count[piece_index]})"
        )

        # Detect poisoned piece — multiple unique peers all fail this piece
        unique_peers_failing = len(self._fail_peers[piece_index])
        if unique_peers_failing >= self.POISON_THRESHOLD and piece_index not in self._poisoned_pieces:
            self._poisoned_pieces.add(piece_index)
            logger.error(
                f"[Validator] Piece {piece_index} marked POISONED "
                f"({unique_peers_failing} peers failed this piece)"
            )
