from __future__ import annotations

import time
from typing import Optional

from loguru import logger

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False


class ReputationSystem:
    """
    Maintains a trust score (0.0 – 1.0) for each peer identified by peer_id.

    Scores decay toward 0.5 over time (neutral prior).
    Backed by Redis for persistence; falls back to in-memory if Redis
    is unavailable.
    """

    INITIAL_SCORE = 0.5
    SUCCESS_DELTA = 0.02
    FAILURE_DELTA = 0.05
    DECAY_RATE = 0.001       # per hour
    DECAY_INTERVAL = 3600    # seconds

    def __init__(self, config: dict):
        self.config = config["security"]
        self._scores: dict[str, float] = {}
        self._last_seen: dict[str, float] = {}
        self._redis: Optional[object] = None
        self._blacklist: set[str] = set()
        self._init_redis(config.get("redis", {}))

    # ------------------------------------------------------------------ #
    # Score management                                                     #
    # ------------------------------------------------------------------ #

    def record_success(self, peer_id: bytes):
        key = peer_id.hex() if isinstance(peer_id, bytes) else str(peer_id)
        score = self._get(key)
        new_score = min(1.0, score + self.SUCCESS_DELTA)
        self._set(key, new_score)

    def record_failure(self, peer_id: bytes):
        key = peer_id.hex() if isinstance(peer_id, bytes) else str(peer_id)
        score = self._get(key)
        new_score = max(0.0, score - self.FAILURE_DELTA)
        self._set(key, new_score)

        if new_score < self.config.get("blacklist_threshold", 0.15):
            self._blacklist.add(key)
            logger.warning(f"[Reputation] Auto-blacklisted peer {key[:8]}... (score={new_score:.3f})")

    def get_score(self, peer_id: bytes | str) -> float:
        key = peer_id.hex() if isinstance(peer_id, bytes) else str(peer_id)
        return self._apply_decay(key, self._get(key))

    def is_blacklisted(self, peer_id: bytes | str) -> bool:
        key = peer_id.hex() if isinstance(peer_id, bytes) else str(peer_id)
        return key in self._blacklist

    def trust_level(self, peer_id: bytes | str) -> str:
        score = self.get_score(peer_id)
        if score >= 0.8:
            return "trusted"
        if score >= 0.5:
            return "neutral"
        if score >= 0.3:
            return "suspicious"
        return "malicious"

    def get_all_scores(self) -> dict[str, float]:
        return {k: self._apply_decay(k, v) for k, v in self._scores.items()}

    def remove_blacklist(self, peer_id: bytes | str):
        key = peer_id.hex() if isinstance(peer_id, bytes) else str(peer_id)
        self._blacklist.discard(key)
        self._set(key, self.INITIAL_SCORE)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _get(self, key: str) -> float:
        if self._redis:
            try:
                val = self._redis.get(f"swyft:rep:{key}")
                return float(val) if val else self.INITIAL_SCORE
            except Exception:
                pass
        return self._scores.get(key, self.INITIAL_SCORE)

    def _set(self, key: str, score: float):
        self._scores[key] = score
        self._last_seen[key] = time.time()
        if self._redis:
            try:
                ttl = self.config.get("ttl_peer_reputation", 86400)
                self._redis.setex(f"swyft:rep:{key}", ttl, str(score))
            except Exception:
                pass

    def _apply_decay(self, key: str, score: float) -> float:
        last = self._last_seen.get(key, time.time())
        hours_elapsed = (time.time() - last) / 3600
        if hours_elapsed < 1:
            return score
        # decay toward 0.5
        decay = self.DECAY_RATE * hours_elapsed
        if score > 0.5:
            return max(0.5, score - decay)
        else:
            return min(0.5, score + decay)

    def _init_redis(self, redis_cfg: dict):
        if not _REDIS_AVAILABLE or not redis_cfg:
            return
        try:
            self._redis = redis.Redis(
                host=redis_cfg.get("host", "localhost"),
                port=redis_cfg.get("port", 6379),
                db=redis_cfg.get("db", 0),
                password=redis_cfg.get("password"),
                decode_responses=True,
                socket_connect_timeout=2,
            )
            self._redis.ping()
            logger.info("[Reputation] Connected to Redis")
        except Exception as e:
            logger.warning(f"[Reputation] Redis unavailable ({e}), using in-memory store")
            self._redis = None
