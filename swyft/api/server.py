from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from swyft.core.torrent_engine import TorrentEngine


# ------------------------------------------------------------------ #
# Request / Response models                                            #
# ------------------------------------------------------------------ #

class AddTorrentRequest(BaseModel):
    torrent_path: str
    output_dir: str = "./downloads"


class PeerActionRequest(BaseModel):
    ip: str
    port: int
    action: str     # "ban" | "remove"


# ------------------------------------------------------------------ #
# App factory                                                          #
# ------------------------------------------------------------------ #

def create_app(config: dict) -> FastAPI:
    app = FastAPI(
        title="Swyft API",
        description="Intelligent P2P Network Analyzer & Optimizer",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.get("api", {}).get("cors_origins", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Single active engine (extend to multi-torrent if needed)
    _engine: Optional[TorrentEngine] = None
    _engine_lock = asyncio.Lock()
    _ws_clients: list[WebSocket] = []

    # ------------------------------------------------------------------ #
    # Health                                                               #
    # ------------------------------------------------------------------ #

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "swyft"}

    # ------------------------------------------------------------------ #
    # Torrent management                                                   #
    # ------------------------------------------------------------------ #

    @app.post("/torrent/add")
    async def add_torrent(req: AddTorrentRequest):
        nonlocal _engine
        async with _engine_lock:
            if _engine and _engine.running:
                raise HTTPException(400, "A download is already in progress")
            _engine = TorrentEngine(config)

        from pathlib import Path
        asyncio.create_task(
            _engine.start(Path(req.torrent_path), Path(req.output_dir))
        )
        return {"status": "started", "torrent": req.torrent_path}

    @app.post("/torrent/stop")
    async def stop_torrent():
        if not _engine:
            raise HTTPException(404, "No active torrent")
        await _engine.stop()
        return {"status": "stopped"}

    @app.get("/torrent/status")
    async def torrent_status():
        if not _engine:
            return {"status": "idle"}
        return _engine.get_status()

    # ------------------------------------------------------------------ #
    # Peers                                                                #
    # ------------------------------------------------------------------ #

    @app.get("/peers")
    async def list_peers():
        if not _engine:
            return {"peers": []}
        peers = _engine.peer_manager.get_all_peers()
        return {
            "total": len(peers),
            "connected": sum(1 for p in peers if p.connected),
            "peers": [
                {
                    "ip": p.ip,
                    "port": p.port,
                    "connected": p.connected,
                    "latency_ms": round(p.latency_ms, 1) if p.latency_ms != float("inf") else None,
                    "download_speed_mbps": round(p.download_speed_bps / 1e6, 3),
                    "reliability": round(p.reliability_score, 3),
                    "pieces_received": p.pieces_received,
                    "pieces_failed": p.pieces_failed,
                    "timeouts": p.timeouts,
                    "trust_level": _engine.reputation.trust_level(p.peer_id or b""),
                    "composite_score": round(p.composite_score, 3),
                }
                for p in peers
            ],
        }

    @app.post("/peers/action")
    async def peer_action(req: PeerActionRequest):
        if not _engine:
            raise HTTPException(404, "No active torrent")
        peer = next(
            (p for p in _engine.peer_manager.get_all_peers()
             if p.ip == req.ip and p.port == req.port),
            None,
        )
        if not peer:
            raise HTTPException(404, "Peer not found")

        if req.action == "ban":
            _engine.peer_manager.ban_peer(peer, reason="manual ban via API")
        elif req.action == "remove":
            _engine.peer_manager.remove_peer(peer)
        else:
            raise HTTPException(400, f"Unknown action: {req.action}")

        return {"status": "ok", "action": req.action, "peer": f"{req.ip}:{req.port}"}

    # ------------------------------------------------------------------ #
    # Pieces                                                               #
    # ------------------------------------------------------------------ #

    @app.get("/pieces")
    async def pieces_status():
        if not _engine or not _engine.piece_manager:
            return {"pieces": []}
        pm = _engine.piece_manager
        return {
            "total": pm.total_pieces,
            "completed": pm.completed_count(),
            "missing": pm.missing_count(),
            "progress": round(pm.progress() * 100, 2),
            "pieces": [
                {"index": p.index, "state": p.state.value, "retries": p.retry_count}
                for p in pm.pieces
            ],
        }

    # ------------------------------------------------------------------ #
    # ML / Swarm                                                           #
    # ------------------------------------------------------------------ #

    @app.get("/swarm")
    async def swarm_analysis():
        if not _engine:
            return {}
        return _engine.swarm_analyzer.swarm_summary()

    @app.get("/ml/peer-scores")
    async def peer_scores():
        if not _engine:
            return {"scores": []}
        peers = _engine.peer_manager.get_available_peers()
        scored = _engine.peer_selector.score_peers(peers)
        return {
            "scores": [
                {"ip": p.ip, "port": p.port, "score": round(s, 4)}
                for p, s in scored
            ]
        }

    # ------------------------------------------------------------------ #
    # Security                                                             #
    # ------------------------------------------------------------------ #

    @app.get("/security/threats")
    async def security_threats():
        if not _engine:
            return {"events": []}
        events = _engine.threat_detector.get_recent_events(50)
        return {
            "total_events": len(_engine.threat_detector._events),
            "threat_counts": _engine.threat_detector.threat_count_by_type(),
            "recent": [
                {
                    "peer": e.peer_key,
                    "type": e.threat_type.value,
                    "severity": round(e.severity, 3),
                    "details": e.details,
                    "timestamp": e.timestamp,
                }
                for e in events
            ],
        }

    @app.get("/security/reputation")
    async def reputation():
        if not _engine:
            return {"scores": {}}
        scores = _engine.reputation.get_all_scores()
        return {
            "scores": {k: round(v, 4) for k, v in scores.items()},
            "blacklisted_count": len(_engine.reputation._blacklist),
        }

    # ------------------------------------------------------------------ #
    # Analytics                                                            #
    # ------------------------------------------------------------------ #

    @app.get("/metrics")
    async def metrics():
        if not _engine:
            return {}
        return _engine.metrics.generate_report()

    # ------------------------------------------------------------------ #
    # WebSocket — live feed                                                #
    # ------------------------------------------------------------------ #

    @app.websocket("/ws")
    async def websocket_feed(ws: WebSocket):
        await ws.accept()
        _ws_clients.append(ws)
        logger.info(f"[WS] Client connected ({len(_ws_clients)} total)")
        try:
            while True:
                payload = {}
                if _engine:
                    payload = {
                        "status": _engine.get_status(),
                        "metrics": _engine.metrics.generate_report(),
                        "swarm": _engine.swarm_analyzer.swarm_summary(),
                        "threats": _engine.threat_detector.threat_count_by_type(),
                    }
                await ws.send_text(json.dumps(payload))
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            _ws_clients.remove(ws)
            logger.info(f"[WS] Client disconnected ({len(_ws_clients)} remaining)")

    return app
