import pytest
from swyft.security.reputation_system import ReputationSystem

CONFIG = {
    "security": {
        "blacklist_threshold": 0.15,
        "ttl_peer_reputation": 86400,
    }
}


def make_rs() -> ReputationSystem:
    return ReputationSystem(CONFIG)


def test_initial_score():
    rs = make_rs()
    score = rs.get_score(b"\x01" * 20)
    assert score == 0.5


def test_success_increases_score():
    rs = make_rs()
    pid = b"\x01" * 20
    for _ in range(5):
        rs.record_success(pid)
    assert rs.get_score(pid) > 0.5


def test_failure_decreases_score():
    rs = make_rs()
    pid = b"\x02" * 20
    for _ in range(5):
        rs.record_failure(pid)
    assert rs.get_score(pid) < 0.5


def test_auto_blacklist():
    rs = make_rs()
    pid = b"\x03" * 20
    # Force score below blacklist_threshold (0.15)
    for _ in range(20):
        rs.record_failure(pid)
    assert rs.is_blacklisted(pid)


def test_trust_level_labels():
    rs = make_rs()
    pid = b"\x04" * 20
    for _ in range(20):
        rs.record_success(pid)
    assert rs.trust_level(pid) == "trusted"


def test_remove_from_blacklist():
    rs = make_rs()
    pid = b"\x05" * 20
    for _ in range(20):
        rs.record_failure(pid)
    assert rs.is_blacklisted(pid)
    rs.remove_blacklist(pid)
    assert not rs.is_blacklisted(pid)
    assert rs.get_score(pid) == 0.5
