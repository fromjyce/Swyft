from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import numpy as np
from loguru import logger

try:
    from sklearn.cluster import KMeans, DBSCAN
    from sklearn.preprocessing import StandardScaler
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

if TYPE_CHECKING:
    from swyft.core.peer_manager import PeerInfo


@dataclass
class ClusterInfo:
    cluster_id: int
    label: str                  # "fast", "slow", "unreliable", "normal"
    peer_count: int
    avg_latency_ms: float
    avg_speed_mbps: float
    avg_reliability: float
    centroid: list[float] = field(default_factory=list)


class SwarmAnalyzer:
    """
    Clusters the peer swarm to identify:
      - fast clusters (high bandwidth, low latency)
      - slow clusters (throttled / limited peers)
      - unreliable clusters (high failure rate)

    Uses K-Means for broad clustering and DBSCAN to detect outlier groups.
    """

    def __init__(self, config: dict):
        cfg = config["ml"]["swarm_analyzer"]
        self.n_clusters: int = cfg.get("n_clusters", 5)
        self.update_interval: float = cfg.get("update_interval", 60)
        self._last_update: float = 0.0
        self._clusters: list[ClusterInfo] = []
        self._peer_cluster_map: dict[str, int] = {}   # peer.key -> cluster_id
        self._scaler = StandardScaler() if _SKLEARN_AVAILABLE else None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def update(self, peers: list["PeerInfo"]):
        now = time.time()
        if (now - self._last_update) < self.update_interval:
            return
        self._last_update = now

        connected = [p for p in peers if p.connected]
        if len(connected) < self.n_clusters:
            return

        self._run_clustering(connected)

    def get_clusters(self) -> list[ClusterInfo]:
        return list(self._clusters)

    def get_peer_cluster(self, peer: "PeerInfo") -> Optional[int]:
        return self._peer_cluster_map.get(peer.key)

    def get_fast_peers(self, peers: list["PeerInfo"]) -> list["PeerInfo"]:
        fast_ids = {
            c.cluster_id for c in self._clusters if c.label == "fast"
        }
        return [p for p in peers if self._peer_cluster_map.get(p.key) in fast_ids]

    def swarm_summary(self) -> dict:
        if not self._clusters:
            return {"clusters": 0, "analyzed_peers": 0}
        return {
            "clusters": len(self._clusters),
            "fast_clusters": sum(1 for c in self._clusters if c.label == "fast"),
            "slow_clusters": sum(1 for c in self._clusters if c.label == "slow"),
            "unreliable_clusters": sum(1 for c in self._clusters if c.label == "unreliable"),
            "cluster_details": [
                {
                    "id": c.cluster_id,
                    "label": c.label,
                    "peers": c.peer_count,
                    "avg_latency_ms": round(c.avg_latency_ms, 1),
                    "avg_speed_mbps": round(c.avg_speed_mbps, 3),
                    "avg_reliability": round(c.avg_reliability, 3),
                }
                for c in self._clusters
            ],
        }

    # ------------------------------------------------------------------ #
    # Clustering                                                           #
    # ------------------------------------------------------------------ #

    def _run_clustering(self, peers: list["PeerInfo"]):
        if not _SKLEARN_AVAILABLE:
            logger.debug("[SwarmAnalyzer] scikit-learn not available")
            return

        features = np.array(
            [
                [
                    p.latency_ms if p.latency_ms != float("inf") else 2000.0,
                    p.download_speed_bps / 1e6,
                    p.reliability_score,
                    float(p.timeouts),
                ]
                for p in peers
            ],
            dtype=np.float32,
        )

        try:
            scaled = self._scaler.fit_transform(features)
            n = min(self.n_clusters, len(peers))
            kmeans = KMeans(n_clusters=n, n_init="auto", random_state=42)
            labels = kmeans.fit_predict(scaled)

            self._clusters = []
            self._peer_cluster_map = {}

            for cid in range(n):
                mask = labels == cid
                cluster_peers = [p for p, m in zip(peers, mask) if m]
                if not cluster_peers:
                    continue

                avg_lat = float(np.mean([p.latency_ms if p.latency_ms != float("inf") else 2000 for p in cluster_peers]))
                avg_spd = float(np.mean([p.download_speed_bps / 1e6 for p in cluster_peers]))
                avg_rel = float(np.mean([p.reliability_score for p in cluster_peers]))

                label = self._classify_cluster(avg_lat, avg_spd, avg_rel)
                centroid = kmeans.cluster_centers_[cid].tolist()

                ci = ClusterInfo(
                    cluster_id=cid,
                    label=label,
                    peer_count=len(cluster_peers),
                    avg_latency_ms=avg_lat,
                    avg_speed_mbps=avg_spd,
                    avg_reliability=avg_rel,
                    centroid=centroid,
                )
                self._clusters.append(ci)

                for p in cluster_peers:
                    self._peer_cluster_map[p.key] = cid

            logger.debug(f"[SwarmAnalyzer] Clustered {len(peers)} peers into {n} groups")
        except Exception as e:
            logger.debug(f"[SwarmAnalyzer] Clustering failed: {e}")

    @staticmethod
    def _classify_cluster(avg_lat: float, avg_spd: float, avg_rel: float) -> str:
        if avg_spd > 1.0 and avg_lat < 200 and avg_rel > 0.8:
            return "fast"
        if avg_rel < 0.3:
            return "unreliable"
        if avg_spd < 0.1 or avg_lat > 800:
            return "slow"
        return "normal"
