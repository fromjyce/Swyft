from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from loguru import logger
from sklearn.preprocessing import MinMaxScaler

try:
    import xgboost as xgb
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False
    logger.warning("[PeerSelector] xgboost not available, falling back to heuristic scoring")

from swyft.core.peer_manager import PeerInfo

FEATURE_NAMES = [
    "latency_ms",
    "download_speed_mbps",
    "upload_speed_mbps",
    "reliability_score",
    "pieces_received",
    "pieces_failed",
    "timeouts",
    "seconds_since_active",
    "is_connected",
    "not_choking",
]


class PeerSelector:
    """
    Scores and ranks peers using XGBoost (or heuristic fallback).

    Training labels are derived from observed download efficiency:
    pieces_received / (pieces_received + pieces_failed + timeouts).
    The model is retrained periodically on accumulated peer history.
    """

    def __init__(self, config: dict):
        self.config = config["ml"]["peer_selector"]
        self.model: Optional[object] = None
        self.scaler = MinMaxScaler()
        self._training_buffer: list[tuple[list[float], float]] = []
        self._last_train_time: float = 0.0
        self._model_path = Path(self.config.get("model_path", "models/peer_selector.pkl"))

        self._try_load_model()

    # ------------------------------------------------------------------ #
    # Scoring                                                              #
    # ------------------------------------------------------------------ #

    def score_peers(self, peers: list[PeerInfo]) -> list[tuple[PeerInfo, float]]:
        if not peers:
            return []

        features = np.array([p.to_feature_vector() for p in peers], dtype=np.float32)

        if self.model is not None and _XGB_AVAILABLE:
            scores = self._predict_xgb(features)
        else:
            scores = self._heuristic_scores(peers)

        self._buffer_training_data(peers, scores)
        self._maybe_retrain()

        return sorted(zip(peers, scores), key=lambda x: x[1], reverse=True)

    def select_top_k(self, scored: list[tuple[PeerInfo, float]], k: int) -> list[PeerInfo]:
        return [peer for peer, _ in scored[:k]]

    # ------------------------------------------------------------------ #
    # XGBoost inference                                                    #
    # ------------------------------------------------------------------ #

    def _predict_xgb(self, features: np.ndarray) -> list[float]:
        try:
            scaled = self.scaler.transform(features)
            raw = self.model.predict(scaled)
            return [float(s) for s in raw]
        except Exception as e:
            logger.debug(f"[PeerSelector] XGB predict failed: {e}, using heuristic")
            return self._heuristic_scores_from_features(features)

    def _heuristic_scores(self, peers: list[PeerInfo]) -> list[float]:
        return [p.composite_score for p in peers]

    def _heuristic_scores_from_features(self, features: np.ndarray) -> list[float]:
        scores = []
        for f in features:
            latency_norm = max(0.0, 1.0 - f[0] / 2000.0)
            speed_norm = min(f[1] / 10.0, 1.0)
            reliability = f[3]
            score = 0.35 * latency_norm + 0.40 * speed_norm + 0.25 * reliability
            scores.append(float(score))
        return scores

    # ------------------------------------------------------------------ #
    # Training                                                             #
    # ------------------------------------------------------------------ #

    def _buffer_training_data(self, peers: list[PeerInfo], scores: list[float]):
        for peer, score in zip(peers, scores):
            total = peer.pieces_received + peer.pieces_failed + peer.timeouts
            if total > 0:
                label = peer.pieces_received / total
                self._training_buffer.append((peer.to_feature_vector(), label))

        max_buffer = 5000
        if len(self._training_buffer) > max_buffer:
            self._training_buffer = self._training_buffer[-max_buffer:]

    def _maybe_retrain(self):
        interval = self.config.get("retrain_interval", 3600)
        min_samples = self.config.get("min_training_samples", 50)
        if (
            _XGB_AVAILABLE
            and len(self._training_buffer) >= min_samples
            and (time.time() - self._last_train_time) > interval
        ):
            self._retrain()

    def _retrain(self):
        logger.info(f"[PeerSelector] Retraining on {len(self._training_buffer)} samples")
        X = np.array([f for f, _ in self._training_buffer], dtype=np.float32)
        y = np.array([label for _, label in self._training_buffer], dtype=np.float32)

        X_scaled = self.scaler.fit_transform(X)

        self.model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            verbosity=0,
        )
        self.model.fit(X_scaled, y)
        self._last_train_time = time.time()
        self._save_model()
        logger.info("[PeerSelector] Model retrained successfully")

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def _save_model(self):
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "scaler": self.scaler}, self._model_path)

    def _try_load_model(self):
        if self._model_path.exists():
            try:
                saved = joblib.load(self._model_path)
                self.model = saved["model"]
                self.scaler = saved["scaler"]
                logger.info(f"[PeerSelector] Loaded model from {self._model_path}")
            except Exception as e:
                logger.warning(f"[PeerSelector] Failed to load model: {e}")
