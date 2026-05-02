from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import bencodepy
from loguru import logger

from swyft.core.peer_manager import PeerManager, PeerInfo
from swyft.core.piece_manager import PieceManager
from swyft.core.network_layer import NetworkLayer
from swyft.core.tracker import TrackerClient
from swyft.core.dht import DHTNode
from swyft.ml.peer_selector import PeerSelector
from swyft.ml.swarm_analyzer import SwarmAnalyzer
from swyft.security.threat_detector import ThreatDetector
from swyft.security.reputation_system import ReputationSystem
from swyft.analytics.metrics_collector import MetricsCollector


@dataclass
class TorrentMetadata:
    info_hash: bytes
    name: str
    total_size: int
    piece_length: int
    pieces: list[bytes]
    files: list[dict]
    tracker_url: str
    announce_list: list[str] = field(default_factory=list)
    private: bool = False


class TorrentEngine:
    """
    Orchestrates all subsystems for a single torrent download.

    Flow:
      parse_torrent_file → start → _download_loop → _assemble_files
    """

    def __init__(self, config: dict):
        self.config = config
        self.peer_manager = PeerManager(config)
        self.network = NetworkLayer(config)
        self.tracker = TrackerClient(config)
        self.dht = DHTNode(config)
        self.peer_selector = PeerSelector(config)
        self.swarm_analyzer = SwarmAnalyzer(config)
        self.threat_detector = ThreatDetector(config)
        self.reputation = ReputationSystem(config)
        self.metrics = MetricsCollector()

        self.metadata: Optional[TorrentMetadata] = None
        self.piece_manager: Optional[PieceManager] = None
        self.peer_id: bytes = self._make_peer_id()
        self.running: bool = False
        self._download_task: Optional[asyncio.Task] = None
        self._start_time: float = 0.0
        self._last_expand: float = 0.0
        self._output_dir: Optional[Path] = None
        self._file_handles: dict[str, object] = {}

    # ------------------------------------------------------------------ #
    # Setup helpers                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _make_peer_id() -> bytes:
        return b"-SY0100-" + os.urandom(12)

    # ------------------------------------------------------------------ #
    # Torrent file parsing                                                 #
    # ------------------------------------------------------------------ #

    def parse_torrent_file(self, path: Path) -> TorrentMetadata:
        with open(path, "rb") as fh:
            raw = fh.read()

        data = bencodepy.decode(raw)
        info = data[b"info"]
        info_hash = hashlib.sha1(bencodepy.encode(info)).digest()

        piece_length: int = info[b"piece length"]
        raw_pieces: bytes = info[b"pieces"]
        pieces = [raw_pieces[i:i + 20] for i in range(0, len(raw_pieces), 20)]

        if b"files" in info:
            files: list[dict] = []
            offset = 0
            for f in info[b"files"]:
                length = f[b"length"]
                path_parts = [p.decode("utf-8", errors="replace") for p in f[b"path"]]
                files.append({"path": "/".join(path_parts), "length": length, "offset": offset})
                offset += length
            total_size = offset
        else:
            total_size = info[b"length"]
            files = [{"path": info[b"name"].decode("utf-8", errors="replace"), "length": total_size, "offset": 0}]

        tracker_url = data.get(b"announce", b"").decode("utf-8", errors="replace")
        announce_list = [
            tier[0].decode("utf-8", errors="replace")
            for tier in data.get(b"announce-list", [])
            if tier
        ]

        self.metadata = TorrentMetadata(
            info_hash=info_hash,
            name=info[b"name"].decode("utf-8", errors="replace"),
            total_size=total_size,
            piece_length=piece_length,
            pieces=pieces,
            files=files,
            tracker_url=tracker_url,
            announce_list=announce_list,
            private=bool(info.get(b"private", 0)),
        )
        self.piece_manager = PieceManager(self.metadata)
        logger.info(
            f"[Engine] Parsed '{self.metadata.name}' "
            f"({total_size / 1e9:.2f} GB, {len(pieces)} pieces)"
        )
        return self.metadata

    # ------------------------------------------------------------------ #
    # Start / Stop                                                         #
    # ------------------------------------------------------------------ #

    async def start(self, torrent_path: Path, output_dir: Path):
        if self.metadata is None:
            self.parse_torrent_file(torrent_path)

        self.running = True
        self._start_time = time.monotonic()
        self.metrics.start_session(self.metadata.info_hash.hex())
        logger.info(f"[Engine] Starting: {self.metadata.name}")

        # DHT (skip for private torrents)
        if not self.metadata.private:
            asyncio.create_task(self.dht.start(self.metadata.info_hash))

        # Announce to all trackers
        trackers = list({self.metadata.tracker_url} | set(self.metadata.announce_list))
        trackers = [t for t in trackers if t.startswith(("http", "udp"))]

        peer_results = await asyncio.gather(
            *[
                self.tracker.announce(
                    tracker_url=t,
                    info_hash=self.metadata.info_hash,
                    peer_id=self.peer_id,
                    port=self.config["dht"]["port"],
                    uploaded=0,
                    downloaded=0,
                    left=self.metadata.total_size,
                )
                for t in trackers
            ],
            return_exceptions=True,
        )

        for result in peer_results:
            if isinstance(result, list):
                for peer_addr in result:
                    self.peer_manager.add_peer(peer_addr["ip"], peer_addr["port"])

        logger.info(f"[Engine] Initial peer pool: {self.peer_manager.peer_count()}")

        self._download_task = asyncio.create_task(self._download_loop(output_dir))
        await self._download_task

    async def stop(self):
        self.running = False
        if self._download_task and not self._download_task.done():
            self._download_task.cancel()
        for fh in self._file_handles.values():
            try:
                fh.flush()
                fh.close()
            except OSError:
                pass
        self._file_handles.clear()
        await self.network.close_all()
        await self.dht.stop()
        logger.info("[Engine] Stopped")

    # ------------------------------------------------------------------ #
    # Main download loop                                                   #
    # ------------------------------------------------------------------ #

    async def _download_loop(self, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        self._output_dir = output_dir
        self._open_output_files(output_dir)

        while self.running and not self.piece_manager.is_complete():
            # Rate-limit connection expansion to once per 5 s
            now = time.monotonic()
            if now - self._last_expand >= 5.0:
                asyncio.create_task(self._expand_connections())
                self._last_expand = now

            available = self.peer_manager.get_available_peers()
            if not available:
                await asyncio.sleep(2)
                continue

            # ML peer scoring + selection
            scored = self.peer_selector.score_peers(available)
            chosen = self.peer_selector.select_top_k(scored, k=self.config["ml"]["peer_selector"]["top_k"])

            # Swarm analysis (runs periodically)
            self.swarm_analyzer.update(self.peer_manager.get_all_peers())

            # Dispatch piece requests concurrently
            tasks = []
            for peer in chosen:
                pieces = self.piece_manager.get_pieces_for_peer(peer, max_pieces=5)
                if pieces:
                    tasks.append(asyncio.create_task(self._fetch_pieces(peer, pieces)))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Metrics
            self.metrics.update(
                downloaded=self.piece_manager.bytes_downloaded(),
                total=self.metadata.total_size,
                peer_count=self.peer_manager.peer_count(),
                active_connections=self.network.connection_count(),
            )

            await asyncio.sleep(0.05)

        if self.piece_manager.is_complete():
            elapsed = time.monotonic() - self._start_time
            avg_mbps = self.metadata.total_size / elapsed / 1e6
            logger.success(
                f"[Engine] Complete: {self.metadata.name} "
                f"in {elapsed:.1f}s ({avg_mbps:.2f} MB/s avg)"
            )
            await self._assemble_files(output_dir)
            await self.tracker.announce(
                tracker_url=self.metadata.tracker_url,
                info_hash=self.metadata.info_hash,
                peer_id=self.peer_id,
                port=self.config["dht"]["port"],
                uploaded=0,
                downloaded=self.metadata.total_size,
                left=0,
                event="completed",
            )

    # ------------------------------------------------------------------ #
    # Piece fetching                                                       #
    # ------------------------------------------------------------------ #

    async def _fetch_pieces(self, peer: PeerInfo, piece_indices: list[int]):
        for idx in piece_indices:
            self.piece_manager.mark_downloading(idx, peer.peer_id or b"")
            t0 = time.monotonic()

            data = await self.network.request_piece(
                peer=peer,
                piece_index=idx,
                piece_length=self.piece_manager.pieces[idx].length,
                timeout=self.config["torrent"]["request_timeout"],
            )

            elapsed = time.monotonic() - t0

            if data is None:
                self.piece_manager.mark_failed(idx)
                self.peer_manager.record_timeout(peer)
                continue

            # Security: hash validation
            if not self.piece_manager.validate_piece(idx, data):
                self.piece_manager.mark_failed(idx)
                self.reputation.record_failure(peer.peer_id or b"unknown")
                self.threat_detector.flag_bad_data(peer)
                logger.warning(f"[Engine] Bad piece {idx} from {peer.ip}")
                if self.reputation.get_score(peer.peer_id or b"unknown") < self.config["security"]["blacklist_threshold"]:
                    self.peer_manager.ban_peer(peer, reason="repeated bad pieces")
                continue

            self.piece_manager.mark_complete(idx, data)
            self._write_piece(idx, data)
            self.peer_manager.update_download_speed(peer, len(data), elapsed)
            self.reputation.record_success(peer.peer_id or b"unknown")
            self.metrics.record_piece(peer=peer, piece_idx=idx, bytes_count=len(data), elapsed=elapsed)

    # ------------------------------------------------------------------ #
    # Connection expansion                                                 #
    # ------------------------------------------------------------------ #

    async def _expand_connections(self):
        max_conn = self.config["torrent"]["max_connections"]
        if self.network.connection_count() >= max_conn:
            return
        needed = min(5, max_conn - self.network.connection_count())
        candidates = [p for p in self.peer_manager.get_all_peers() if not p.connected][:needed]
        await asyncio.gather(
            *[
                self.network.connect(p, self.metadata.info_hash, self.peer_id)
                for p in candidates
            ],
            return_exceptions=True,
        )

    # ------------------------------------------------------------------ #
    # Incremental disk I/O                                                 #
    # ------------------------------------------------------------------ #

    def _open_output_files(self, output_dir: Path):
        """Pre-allocate output files so pieces can be written at any offset."""
        for file_info in self.metadata.files:
            dest = output_dir / file_info["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                # Sparse pre-allocation — seek-and-write one null byte
                with open(dest, "wb") as fh:
                    if file_info["length"] > 0:
                        fh.seek(file_info["length"] - 1)
                        fh.write(b"\x00")
            self._file_handles[file_info["path"]] = open(dest, "r+b")

    def _write_piece(self, piece_idx: int, data: bytes):
        """Write a completed piece directly to the appropriate output file(s).

        A piece may span multiple files; we split accordingly.
        """
        if not self._output_dir or not self._file_handles:
            return

        piece_offset_global = piece_idx * self.metadata.piece_length
        piece_end_global = piece_offset_global + len(data)

        for file_info in self.metadata.files:
            f_start = file_info["offset"]
            f_end = f_start + file_info["length"]

            overlap_start = max(piece_offset_global, f_start)
            overlap_end = min(piece_end_global, f_end)
            if overlap_start >= overlap_end:
                continue

            fh = self._file_handles.get(file_info["path"])
            if fh is None:
                continue

            slice_in_piece = slice(overlap_start - piece_offset_global, overlap_end - piece_offset_global)
            write_offset_in_file = overlap_start - f_start
            try:
                fh.seek(write_offset_in_file)
                fh.write(data[slice_in_piece])
            except OSError as e:
                logger.error(f"[Engine] Write error for piece {piece_idx}: {e}")

    async def _assemble_files(self, output_dir: Path):
        """Flush and close all file handles — pieces are already written."""
        logger.info("[Engine] Flushing and closing output files")
        for path, fh in self._file_handles.items():
            try:
                fh.flush()
                fh.close()
                logger.info(f"[Engine] Finalised: {output_dir / path}")
            except OSError:
                pass
        self._file_handles.clear()

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    def get_status(self) -> dict:
        if not self.metadata:
            return {"status": "idle"}
        pm = self.piece_manager
        return {
            "status": "downloading" if self.running else "stopped",
            "name": self.metadata.name,
            "info_hash": self.metadata.info_hash.hex(),
            "progress": pm.progress() if pm else 0.0,
            "bytes_downloaded": pm.bytes_downloaded() if pm else 0,
            "total_size": self.metadata.total_size,
            "pieces_done": pm.completed_count() if pm else 0,
            "pieces_total": len(self.metadata.pieces),
            "peers_total": self.peer_manager.peer_count(),
            "peers_active": len(self.peer_manager.get_available_peers()),
            "connections": self.network.connection_count(),
            "download_speed_bps": self.metrics.current_speed(),
            "eta_seconds": self.metrics.eta(),
            "elapsed_seconds": time.monotonic() - self._start_time,
        }
