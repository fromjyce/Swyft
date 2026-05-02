from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

import numpy as np
from loguru import logger

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

if TYPE_CHECKING:
    from swyft.core.peer_manager import PeerInfo


class ThreatType(Enum):
    BAD_DATA = "bad_data"                    # failed hash checks
    ABNORMAL_UPLOAD = "abnormal_upload"      # suspicious upload behaviour
    HIGH_LATENCY_VARIANCE = "high_latency_variance"
    REPEATED_TIMEOUTS = "repeated_timeouts"
    ANOMALOUS_PATTERN = "anomalous_pattern"  # IsolationForest


@dataclass
class ThreatEvent:
    peer_key: str
    threat_type: ThreatType
    severity: float           # 0.0 low … 1.0 critical
    timestamp: float = field(default_factory=time.time)
    details: str = ""


class ThreatDetector:
    """
    Detects malicious or misbehaving peers using a combination of:
      - Rule-based heuristics (bad data, timeouts, upload anomalies)
      - IsolationForest anomaly detection on per-peer feature vectors
    """

    def __init__(self, config: dict):
        self.config = config["security"]
        self._events: list[ThreatEvent] = []
        self._bad_data_counter: dict[str, int] = defaultdict(int)
        self._upload_history: dict[str, list[float]] = defaultdict(list)
        self._feature_buffer: list[list[float]] = []
        self._iso_model: Optional[object] = None
        self._iso_scaler: Optional[object] = None
        self._last_model_fit: float = 0.0

    # ------------------------------------------------------------------ #
    # Event ingestion                                                      #
    # ------------------------------------------------------------------ #

    def flag_bad_data(self, peer: "PeerInfo"):
        self._bad_data_counter[peer.key] += 1
        count = self._bad_data_counter[peer.key]
        severity = min(count / 10.0, 1.0)
        self._record_event(peer.key, ThreatType.BAD_DATA, severity, f"bad_pieces={count}")

    def flag_abnormal_upload(self, peer: "PeerInfo", upload_bps: float):
        history = self._upload_history[peer.key]
        history.append(upload_bps)
        if len(history) > 20:
            history.pop(0)

        if len(history) >= 5:
            mean = np.mean(history[:-1])
            current = history[-1]
            if mean > 0 and abs(current - mean) / mean > 2.0:
                severity = min(abs(current - mean) / mean / 10, 1.0)
                self._record_event(peer.key, ThreatType.ABNORMAL_UPLOAD, severity, f"upload_bps={upload_bps:.0f}")

    def flag_timeout(self, peer: "PeerInfo"):
        if peer.timeouts > 10:
            severity = min(peer.timeouts / 20.0, 1.0)
            self._record_event(peer.key, ThreatType.REPEATED_TIMEOUTS, severity, f"timeouts={peer.timeouts}")

    def analyze_peer(self, peer: "PeerInfo") -> Optional[ThreatEvent]:
        """Run full anomaly detection on a single peer."""
        features = self._extract_features(peer)
        self._feature_buffer.append(features)
        if len(self._feature_buffer) > 2000:
            self._feature_buffer.pop(0)

        # Refit every 500 new samples
        if (
            _SKLEARN_AVAILABLE
            and len(self._feature_buffer) >= 100
            and len(self._feature_buffer) % 100 == 0
        ):
            self._fit_isolation_forest()

        if self._iso_model is not None:
            return self._run_isolation_forest(peer, features)
        return None

    # ------------------------------------------------------------------ #
    # IsolationForest                                                      #
    # ------------------------------------------------------------------ #

    def _fit_isolation_forest(self):
        X = np.array(self._feature_buffer, dtype=np.float32)
        try:
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            model = IsolationForest(
                n_estimators=100,
                contamination=self.config.get("anomaly_contamination", 0.05),
                random_state=42,
            )
            model.fit(X_scaled)
            self._iso_model = model
            self._iso_scaler = scaler
            self._last_model_fit = time.time()
            logger.debug(f"[ThreatDetector] IsolationForest fitted on {len(self._feature_buffer)} samples")
        except Exception as e:
            logger.debug(f"[ThreatDetector] IsolationForest fit failed: {e}")

    def _run_isolation_forest(self, peer: "PeerInfo", features: list[float]) -> Optional[ThreatEvent]:
        try:
            X = np.array([features], dtype=np.float32)
            X_scaled = self._iso_scaler.transform(X)
            prediction = self._iso_model.predict(X_scaled)[0]
            score = -self._iso_model.score_samples(X_scaled)[0]  # higher = more anomalous

            if prediction == -1:
                event = ThreatEvent(
                    peer_key=peer.key,
                    threat_type=ThreatType.ANOMALOUS_PATTERN,
                    severity=min(score, 1.0),
                    details=f"isolation_score={score:.3f}",
                )
                self._events.append(event)
                logger.warning(f"[ThreatDetector] Anomaly detected: {peer.ip} score={score:.3f}")
                return event
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _record_event(self, peer_key: str, threat_type: ThreatType, severity: float, details: str):
        event = ThreatEvent(peer_key=peer_key, threat_type=threat_type, severity=severity, details=details)
        self._events.append(event)
        if severity >= 0.7:
            logger.warning(f"[ThreatDetector] High severity {threat_type.value} from {peer_key}: {details}")

    @staticmethod
    def _extract_features(peer: "PeerInfo") -> list[float]:
        total = peer.pieces_received + peer.pieces_failed
        fail_rate = peer.pieces_failed / total if total > 0 else 0.5
        return [
            peer.latency_ms if peer.latency_ms != float("inf") else 9999.0,
            peer.download_speed_bps / 1e6,
            peer.upload_speed_bps / 1e6,
            float(peer.pieces_received),
            float(peer.pieces_failed),
            fail_rate,
            float(peer.timeouts),
        ]

    def get_recent_events(self, n: int = 50) -> list[ThreatEvent]:
        return sorted(self._events, key=lambda e: e.timestamp, reverse=True)[:n]

    def threat_count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for ev in self._events:
            counts[ev.threat_type.value] += 1
        return dict(counts)

    def is_threat(self, peer: "PeerInfo") -> bool:
        peer_events = [e for e in self._events if e.peer_key == peer.key]
        if not peer_events:
            return False
        max_severity = max(e.severity for e in peer_events)
        return max_severity >= 0.7
