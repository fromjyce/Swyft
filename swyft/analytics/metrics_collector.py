from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from loguru import logger

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False

if TYPE_CHECKING:
    from swyft.core.peer_manager import PeerInfo


@dataclass
class SpeedSample:
    timestamp: float
    bytes_total: int


class MetricsCollector:
    """
    Collects and exposes runtime metrics:
      - Download speed (EWMA + rolling window)
      - Peer churn rate
      - Piece download latency histogram
      - ETA calculation
    Also exposes Prometheus metrics if available.
    """

    SPEED_WINDOW_S = 10     # rolling speed calculation window (seconds)

    def __init__(self):
        self._session_id: Optional[str] = None
        self._session_start: float = 0.0
        self._samples: deque[SpeedSample] = deque(maxlen=200)
        self._last_bytes: int = 0
        self._last_speed_bps: float = 0.0
        self._total_downloaded: int = 0
        self._total_size: int = 0
        self._peer_count_history: deque[tuple[float, int]] = deque(maxlen=200)
        self._piece_latencies: deque[float] = deque(maxlen=500)
        self._active_connections: int = 0

        # Per-peer speed tracking
        self._peer_contributions: dict[str, int] = {}

        if _PROM_AVAILABLE:
            self._init_prometheus()

    # ------------------------------------------------------------------ #
    # Session lifecycle                                                    #
    # ------------------------------------------------------------------ #

    def start_session(self, session_id: str):
        self._session_id = session_id
        self._session_start = time.time()
        logger.info(f"[Metrics] Session started: {session_id}")

    # ------------------------------------------------------------------ #
    # Updates                                                              #
    # ------------------------------------------------------------------ #

    def update(
        self,
        downloaded: int,
        total: int,
        peer_count: int,
        active_connections: int = 0,
    ):
        now = time.time()
        self._total_downloaded = downloaded
        self._total_size = total
        self._active_connections = active_connections
        self._samples.append(SpeedSample(timestamp=now, bytes_total=downloaded))
        self._peer_count_history.append((now, peer_count))

        if _PROM_AVAILABLE:
            try:
                self._g_downloaded.set(downloaded)
                self._g_peers.set(peer_count)
                self._g_progress.set(downloaded / total if total else 0)
            except Exception:
                pass

    def record_piece(self, peer: "PeerInfo", piece_idx: int, bytes_count: int, elapsed: float):
        if elapsed > 0:
            self._piece_latencies.append(elapsed)
        key = peer.key
        self._peer_contributions[key] = self._peer_contributions.get(key, 0) + bytes_count

        if _PROM_AVAILABLE:
            try:
                self._c_pieces.inc()
                self._h_piece_latency.observe(elapsed)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Computed metrics                                                     #
    # ------------------------------------------------------------------ #

    def current_speed(self) -> float:
        """Bytes/s over the last SPEED_WINDOW_S seconds."""
        if len(self._samples) < 2:
            return 0.0
        now = time.time()
        cutoff = now - self.SPEED_WINDOW_S
        recent = [s for s in self._samples if s.timestamp >= cutoff]
        if len(recent) < 2:
            return 0.0
        delta_bytes = recent[-1].bytes_total - recent[0].bytes_total
        delta_time = recent[-1].timestamp - recent[0].timestamp
        if delta_time <= 0:
            return 0.0
        speed = delta_bytes / delta_time
        self._last_speed_bps = speed
        return speed

    def eta(self) -> float:
        """Estimated seconds to completion."""
        remaining = self._total_size - self._total_downloaded
        speed = self.current_speed()
        if speed <= 0 or remaining <= 0:
            return float("inf")
        return remaining / speed

    def peer_churn_rate(self) -> float:
        """Average peer additions/removals per minute over last 5 minutes."""
        now = time.time()
        window = [(t, n) for t, n in self._peer_count_history if now - t <= 300]
        if len(window) < 2:
            return 0.0
        changes = sum(abs(window[i][1] - window[i-1][1]) for i in range(1, len(window)))
        minutes = (window[-1][0] - window[0][0]) / 60
        return changes / minutes if minutes > 0 else 0.0

    def avg_piece_latency(self) -> float:
        if not self._piece_latencies:
            return 0.0
        import statistics
        return statistics.mean(self._piece_latencies)

    def generate_report(self) -> dict:
        elapsed = time.time() - self._session_start if self._session_start else 0
        return {
            "session_id": self._session_id,
            "elapsed_seconds": elapsed,
            "bytes_downloaded": self._total_downloaded,
            "total_bytes": self._total_size,
            "progress_pct": round(self._total_downloaded / self._total_size * 100, 2) if self._total_size else 0,
            "download_speed_bps": self.current_speed(),
            "download_speed_mbps": self.current_speed() / 1e6,
            "eta_seconds": self.eta(),
            "active_connections": self._active_connections,
            "avg_piece_latency_s": self.avg_piece_latency(),
            "peer_churn_per_min": self.peer_churn_rate(),
            "top_peers": sorted(
                self._peer_contributions.items(), key=lambda x: x[1], reverse=True
            )[:5],
        }

    # ------------------------------------------------------------------ #
    # Prometheus setup                                                     #
    # ------------------------------------------------------------------ #

    def _init_prometheus(self):
        try:
            self._c_pieces = Counter("swyft_pieces_total", "Total pieces downloaded")
            self._g_downloaded = Gauge("swyft_bytes_downloaded", "Bytes downloaded")
            self._g_peers = Gauge("swyft_peer_count", "Current peer count")
            self._g_progress = Gauge("swyft_progress_ratio", "Download progress 0-1")
            self._h_piece_latency = Histogram(
                "swyft_piece_latency_seconds",
                "Seconds to download one piece",
                buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
            )
        except Exception:
            pass

    def start_prometheus_server(self, port: int = 9100):
        if _PROM_AVAILABLE:
            try:
                start_http_server(port)
                logger.info(f"[Metrics] Prometheus server on :{port}")
            except Exception as e:
                logger.warning(f"[Metrics] Prometheus server failed: {e}")
