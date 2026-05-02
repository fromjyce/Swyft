import pytest
from swyft.core.peer_manager import PeerManager, PeerInfo


CONFIG = {
    "torrent": {
        "max_peers": 5,
        "max_timeouts": 15,
    }
}


def make_pm() -> PeerManager:
    return PeerManager(CONFIG)


def test_add_peer():
    pm = make_pm()
    peer = pm.add_peer("1.2.3.4", 6881)
    assert peer is not None
    assert peer.ip == "1.2.3.4"
    assert pm.peer_count() == 1


def test_add_duplicate_peer_returns_existing():
    pm = make_pm()
    p1 = pm.add_peer("1.2.3.4", 6881)
    p2 = pm.add_peer("1.2.3.4", 6881)
    assert p1 is p2
    assert pm.peer_count() == 1


def test_blacklist_prevents_add():
    pm = make_pm()
    peer = pm.add_peer("1.2.3.4", 6881)
    pm.ban_peer(peer, reason="test")
    result = pm.add_peer("1.2.3.4", 6881)
    assert result is None
    assert pm.peer_count() == 0


def test_evicts_worst_when_full():
    pm = make_pm()
    for i in range(5):
        p = pm.add_peer(f"10.0.0.{i}", 6881)
        # give them all different scores
        p.pieces_received = i * 10
        p.download_speed_bps = i * 1e5

    # 6th peer should trigger eviction
    pm.add_peer("10.0.1.0", 9999)
    assert pm.peer_count() == 5


def test_latency_ewma_update():
    pm = make_pm()
    peer = pm.add_peer("1.2.3.4", 6881)
    pm.update_latency(peer, 100.0)
    assert peer.latency_ms == 100.0  # first reading: set directly

    pm.update_latency(peer, 200.0)
    # EWMA: 0.7 * 100 + 0.3 * 200 = 130
    assert abs(peer.latency_ms - 130.0) < 0.01


def test_composite_score():
    p = PeerInfo(ip="1.2.3.4", port=6881)
    p.pieces_received = 100
    p.pieces_failed = 5
    p.latency_ms = 50.0
    p.download_speed_bps = 2e6
    score = p.composite_score
    assert 0.0 <= score <= 1.5   # bounded by formula weights
