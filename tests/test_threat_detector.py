import pytest
from unittest.mock import MagicMock
from swyft.security.threat_detector import ThreatDetector, ThreatType


CONFIG = {
    "security": {
        "anomaly_contamination": 0.05,
    }
}


def make_peer(ip="1.2.3.4", port=6881, bad_pieces=0, timeouts=0):
    p = MagicMock()
    p.ip = ip
    p.port = port
    p.key = f"{ip}:{port}"
    p.pieces_received = 100
    p.pieces_failed = bad_pieces
    p.timeouts = timeouts
    p.latency_ms = 50.0
    p.download_speed_bps = 1e6
    p.upload_speed_bps = 0.5e6
    return p


def test_flag_bad_data_records_event():
    td = ThreatDetector(CONFIG)
    peer = make_peer()
    td.flag_bad_data(peer)
    events = td.get_recent_events()
    assert len(events) == 1
    assert events[0].threat_type == ThreatType.BAD_DATA


def test_repeated_bad_data_increases_severity():
    td = ThreatDetector(CONFIG)
    peer = make_peer()
    for _ in range(8):
        td.flag_bad_data(peer)
    events = [e for e in td.get_recent_events() if e.threat_type == ThreatType.BAD_DATA]
    severities = [e.severity for e in events]
    assert severities[-1] >= severities[0]


def test_flag_timeout_high_count():
    td = ThreatDetector(CONFIG)
    peer = make_peer(timeouts=15)
    td.flag_timeout(peer)
    events = td.get_recent_events()
    assert any(e.threat_type == ThreatType.REPEATED_TIMEOUTS for e in events)


def test_is_threat_high_severity():
    td = ThreatDetector(CONFIG)
    peer = make_peer()
    for _ in range(20):
        td.flag_bad_data(peer)
    assert td.is_threat(peer)


def test_threat_count_by_type():
    td = ThreatDetector(CONFIG)
    peer1 = make_peer("1.1.1.1")
    peer2 = make_peer("2.2.2.2")
    td.flag_bad_data(peer1)
    td.flag_bad_data(peer1)
    td.flag_timeout(make_peer("3.3.3.3", timeouts=12))
    counts = td.threat_count_by_type()
    assert counts.get("bad_data", 0) == 2
