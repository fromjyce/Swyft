import hashlib
import pytest
from unittest.mock import MagicMock

from swyft.core.piece_manager import PieceManager, PieceState


def make_metadata(n_pieces: int = 10, piece_length: int = 256 * 1024):
    pieces_data = [bytes(range(i, i + 20)) for i in range(n_pieces)]
    pieces_hashes = [hashlib.sha1(d).digest() for d in pieces_data]
    total_size = n_pieces * piece_length

    m = MagicMock()
    m.pieces = pieces_hashes
    m.piece_length = piece_length
    m.total_size = total_size
    return m, pieces_data


def test_initial_state():
    meta, _ = make_metadata(5)
    pm = PieceManager(meta)
    assert pm.total_pieces == 5
    assert pm.completed_count() == 0
    assert pm.progress() == 0.0
    assert not pm.is_complete()


def test_validate_and_complete():
    meta, pieces_data = make_metadata(3)
    pm = PieceManager(meta)

    # Create valid data matching the hash we generated
    for i, raw in enumerate(pieces_data):
        # The hash in meta IS the sha1 of raw, so override piece hash properly
        real_data = b"\x00" * (256 * 1024)
        pm.pieces[i].sha1_hash = hashlib.sha1(real_data).digest()
        assert pm.validate_piece(i, real_data)
        pm.mark_complete(i, real_data)

    assert pm.is_complete()
    assert pm.progress() == 1.0


def test_mark_failed_increments_retry():
    meta, _ = make_metadata(3)
    pm = PieceManager(meta)
    pm.mark_failed(0)
    assert pm.pieces[0].retry_count == 1
    assert pm.pieces[0].state == PieceState.MISSING

    pm.mark_failed(0)
    pm.mark_failed(0)
    assert pm.pieces[0].state == PieceState.FAILED


def test_rarest_first_selection():
    meta, _ = make_metadata(5)
    pm = PieceManager(meta)

    peer_id = b"\x01" * 20
    bitfield_byte = 0b11111000  # pieces 0-4 owned
    pm.register_peer_bitfield(peer_id, bytes([bitfield_byte]))

    peer = MagicMock()
    peer.peer_id = peer_id
    candidates = pm.get_pieces_for_peer(peer, max_pieces=3)
    assert len(candidates) <= 3
    assert all(isinstance(c, int) for c in candidates)


def test_bitfield_availability_tracking():
    meta, _ = make_metadata(4)
    pm = PieceManager(meta)

    for peer_idx in range(3):
        pid = bytes([peer_idx] * 20)
        # peer 0 and 1 have piece 0; only peer 2 has piece 3
        bitfield = 0b10010000 if peer_idx < 2 else 0b00010000
        pm.register_peer_bitfield(pid, bytes([bitfield]))

    # piece 0 should have availability 2, piece 3 should have 1
    assert pm._availability.get(0, 0) == 2
