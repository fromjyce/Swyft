from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Iterator

from loguru import logger


class PieceState(Enum):
    MISSING = "missing"
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class PieceInfo:
    index: int
    sha1_hash: bytes
    length: int
    state: PieceState = PieceState.MISSING
    data: Optional[bytes] = None
    retry_count: int = 0
    assigned_to: Optional[bytes] = None  # peer_id


class PieceManager:
    def __init__(self, metadata):
        self.metadata = metadata
        self.total_pieces: int = len(metadata.pieces)
        self.piece_length: int = metadata.piece_length
        self.total_size: int = metadata.total_size

        self.pieces: list[PieceInfo] = []
        self._build_piece_list()

        # peer_id -> frozenset of piece indices
        self._peer_bitfields: dict[bytes, set[int]] = {}
        # piece_idx -> number of peers that have it  (for rarest-first)
        self._availability: dict[int, int] = {}

    # ------------------------------------------------------------------ #
    # Setup                                                                #
    # ------------------------------------------------------------------ #

    def _build_piece_list(self):
        last_idx = self.total_pieces - 1
        tail = self.total_size % self.piece_length
        for i, h in enumerate(self.metadata.pieces):
            length = tail if (i == last_idx and tail != 0) else self.piece_length
            self.pieces.append(PieceInfo(index=i, sha1_hash=h, length=length))

    # ------------------------------------------------------------------ #
    # Peer bitfield tracking                                               #
    # ------------------------------------------------------------------ #

    def register_peer_bitfield(self, peer_id: bytes, bitfield: bytes):
        owned: set[int] = set()
        for byte_idx, byte_val in enumerate(bitfield):
            for bit in range(8):
                idx = byte_idx * 8 + bit
                if idx < self.total_pieces and (byte_val >> (7 - bit)) & 1:
                    owned.add(idx)
                    self._availability[idx] = self._availability.get(idx, 0) + 1
        self._peer_bitfields[peer_id] = owned

    def register_peer_have(self, peer_id: bytes, piece_idx: int):
        if peer_id not in self._peer_bitfields:
            self._peer_bitfields[peer_id] = set()
        self._peer_bitfields[peer_id].add(piece_idx)
        self._availability[piece_idx] = self._availability.get(piece_idx, 0) + 1

    def remove_peer(self, peer_id: bytes):
        owned = self._peer_bitfields.pop(peer_id, set())
        for idx in owned:
            if idx in self._availability:
                self._availability[idx] = max(0, self._availability[idx] - 1)

    # ------------------------------------------------------------------ #
    # Piece selection                                                      #
    # ------------------------------------------------------------------ #

    def get_pieces_for_peer(self, peer, max_pieces: int = 5) -> list[int]:
        """Return up to max_pieces indices using rarest-first strategy."""
        peer_id = peer.peer_id
        if not peer_id or peer_id not in self._peer_bitfields:
            return self._fallback_selection(max_pieces)

        peer_has = self._peer_bitfields[peer_id]
        candidates = [
            i for i, p in enumerate(self.pieces)
            if p.state in (PieceState.MISSING, PieceState.FAILED) and i in peer_has
        ]
        candidates.sort(key=lambda i: self._availability.get(i, 0))
        return candidates[:max_pieces]

    def _fallback_selection(self, n: int) -> list[int]:
        return [
            p.index for p in self.pieces
            if p.state in (PieceState.MISSING, PieceState.FAILED)
        ][:n]

    # ------------------------------------------------------------------ #
    # State mutations                                                      #
    # ------------------------------------------------------------------ #

    def validate_piece(self, index: int, data: bytes) -> bool:
        expected = self.pieces[index].sha1_hash
        actual = hashlib.sha1(data).digest()
        if actual != expected:
            logger.warning(f"[PieceManager] Hash mismatch for piece {index}")
        return actual == expected

    def mark_complete(self, index: int, data: bytes = b""):
        p = self.pieces[index]
        p.state = PieceState.COMPLETE
        # Data is written directly to disk via TorrentEngine._write_piece;
        # we don't keep it in RAM to avoid buffering gigabytes.
        p.data = None
        p.assigned_to = None

    def mark_failed(self, index: int):
        p = self.pieces[index]
        p.retry_count += 1
        p.assigned_to = None
        p.state = PieceState.MISSING if p.retry_count < 3 else PieceState.FAILED
        if p.retry_count >= 3:
            logger.warning(f"[PieceManager] Piece {index} failed {p.retry_count} times")

    def mark_downloading(self, index: int, peer_id: bytes):
        p = self.pieces[index]
        if p.state == PieceState.MISSING:
            p.state = PieceState.DOWNLOADING
            p.assigned_to = peer_id

    # ------------------------------------------------------------------ #
    # Stats / iteration                                                    #
    # ------------------------------------------------------------------ #

    def is_complete(self) -> bool:
        return all(p.state == PieceState.COMPLETE for p in self.pieces)

    def completed_count(self) -> int:
        return sum(1 for p in self.pieces if p.state == PieceState.COMPLETE)

    def progress(self) -> float:
        return self.completed_count() / self.total_pieces if self.total_pieces else 0.0

    def bytes_downloaded(self) -> int:
        return sum(p.length for p in self.pieces if p.state == PieceState.COMPLETE)

    def missing_count(self) -> int:
        return sum(1 for p in self.pieces if p.state in (PieceState.MISSING, PieceState.FAILED))

    def iter_pieces(self) -> Iterator[bytes]:
        for piece in self.pieces:
            if piece.data is not None:
                yield piece.data
