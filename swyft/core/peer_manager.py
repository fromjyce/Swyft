from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


@dataclass
class PeerInfo:
    ip: str
    port: int
    peer_id: Optional[bytes] = None

    # Connection state
    connected: bool = False
    handshaked: bool = False

    # Performance metrics (EWMA-smoothed)
    latency_ms: float = float("inf")
    download_speed_bps: float = 0.0
    upload_speed_bps: float = 0.0

    # Reliability counters
    pieces_received: int = 0
    pieces_failed: int = 0
    timeouts: int = 0

    # BitTorrent protocol choke/interest state
    am_choking: bool = True
    am_interested: bool = False
    peer_choking: bool = True
    peer_interested: bool = False

    bitfield: Optional[bytes] = None

    connected_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    @property
    def key(self) -> str:
        return f"{self.ip}:{self.port}"

    @property
    def reliability_score(self) -> float:
        total = self.pieces_received + self.pieces_failed
        return self.pieces_received / total if total > 0 else 0.5

    @property
    def latency_score(self) -> float:
        if self.latency_ms == float("inf"):
            return 0.0
        return max(0.0, 1.0 - self.latency_ms / 2000.0)

    @property
    def composite_score(self) -> float:
        return (
            0.4 * self.reliability_score
            + 0.3 * self.latency_score
            + 0.3 * min(self.download_speed_bps / 1e6, 1.0)
            - 0.1 * min(self.timeouts / 10, 1.0)
        )

    def to_feature_vector(self) -> list[float]:
        return [
            self.latency_ms if self.latency_ms != float("inf") else 9999.0,
            self.download_speed_bps / 1e6,
            self.upload_speed_bps / 1e6,
            self.reliability_score,
            float(self.pieces_received),
            float(self.pieces_failed),
            float(self.timeouts),
            time.time() - self.last_active,
            float(self.connected),
            float(not self.peer_choking),
        ]


class PeerManager:
    def __init__(self, config: dict):
        self.config = config
        self.max_peers: int = config["torrent"]["max_peers"]
        self._peers: dict[str, PeerInfo] = {}
        self._blacklist: set[str] = set()

    # ------------------------------------------------------------------ #
    # Peer lifecycle                                                       #
    # ------------------------------------------------------------------ #

    def add_peer(self, ip: str, port: int) -> Optional[PeerInfo]:
        key = f"{ip}:{port}"
        if key in self._blacklist:
            return None
        if key in self._peers:
            return self._peers[key]
        if len(self._peers) >= self.max_peers:
            self._evict_worst()
        peer = PeerInfo(ip=ip, port=port)
        self._peers[key] = peer
        logger.debug(f"[PeerManager] Added peer {key} (total={len(self._peers)})")
        return peer

    def remove_peer(self, peer: PeerInfo):
        self._peers.pop(peer.key, None)

    def ban_peer(self, peer: PeerInfo, reason: str = ""):
        self._blacklist.add(peer.key)
        self._peers.pop(peer.key, None)
        logger.warning(f"[PeerManager] Banned {peer.key}: {reason}")

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    def get_available_peers(self) -> list[PeerInfo]:
        now = time.time()
        return [
            p for p in self._peers.values()
            if p.connected and not p.peer_choking and (now - p.last_active) < 120
        ]

    def get_all_peers(self) -> list[PeerInfo]:
        return list(self._peers.values())

    def peer_count(self) -> int:
        return len(self._peers)

    def is_blacklisted(self, ip: str, port: int) -> bool:
        return f"{ip}:{port}" in self._blacklist

    # ------------------------------------------------------------------ #
    # Stats updates                                                        #
    # ------------------------------------------------------------------ #

    def record_timeout(self, peer: PeerInfo):
        peer.timeouts += 1
        if peer.timeouts > self.config["torrent"].get("max_timeouts", 15):
            self.remove_peer(peer)

    def update_latency(self, peer: PeerInfo, latency_ms: float):
        if peer.latency_ms == float("inf"):
            peer.latency_ms = latency_ms
        else:
            peer.latency_ms = 0.7 * peer.latency_ms + 0.3 * latency_ms

    def update_download_speed(self, peer: PeerInfo, bytes_recv: int, elapsed_s: float):
        if elapsed_s <= 0:
            return
        sample = bytes_recv / elapsed_s
        peer.download_speed_bps = 0.7 * peer.download_speed_bps + 0.3 * sample
        peer.last_active = time.time()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _evict_worst(self):
        if not self._peers:
            return
        worst = min(self._peers.values(), key=lambda p: p.composite_score)
        logger.debug(f"[PeerManager] Evicting {worst.key} (score={worst.composite_score:.3f})")
        self._peers.pop(worst.key)
