# Swyft — Intelligent P2P Network Analyzer & Optimizer

An enhanced BitTorrent client that layers machine-learning-based peer selection, real-time security threat detection, swarm behaviour analytics, and adaptive download strategies on top of a from-scratch async BitTorrent implementation.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
  - [CLI](#cli)
  - [API Server](#api-server)
  - [Dashboard](#dashboard)
- [Configuration](#configuration)
- [ML Layer](#ml-layer)
- [Security Layer](#security-layer)
- [API Reference](#api-reference)
- [Running Tests](#running-tests)
- [Design Decisions](#design-decisions)

---

## Overview

Swyft is a research-grade BitTorrent client built to demonstrate the intersection of **distributed systems**, **ML-driven optimisation**, and **network security**. It implements the full BitTorrent protocol (BEP 3, BEP 5, BEP 15) from scratch in Python using `asyncio`, then adds intelligence at every layer:

| Layer | What it does |
|---|---|
| **Torrent Engine** | `.torrent` parsing, multi-tracker HTTP/UDP announce, Kademlia DHT peer discovery, async TCP connections, BEP 3 handshake + piece protocol |
| **ML — Peer Selector** | XGBoost ranking model trained online on observed peer performance; falls back to EWMA-weighted heuristic before enough data is collected |
| **ML — Download Optimizer** | Rarity-first piece ordering with per-peer speed weighting; automatic endgame mode (broadcast final pieces to all peers) |
| **ML — Swarm Analyzer** | K-Means clustering of the peer swarm into fast / slow / unreliable / normal groups; updated periodically in the background |
| **Security — Threat Detector** | Rule-based flagging (bad hashes, upload spikes, repeated timeouts) plus IsolationForest anomaly detection |
| **Security — Reputation System** | Trust score (0–1) per peer with exponential decay; backed by Redis for cross-session persistence |
| **Analytics** | Rolling EWMA speed, ETA, Prometheus metrics, piece-latency histograms, peer-churn rate |
| **REST + WebSocket API** | FastAPI server; live dashboard feed via WebSocket push at 1 Hz |
| **Dashboard** | React + D3 SPA with 5 views: Overview, Peers, Pieces, Swarm, Security |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                        CLI (click)                       │
└──────────────┬───────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────┐
│                    TorrentEngine                         │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ PeerManager │  │PieceManager │  │  NetworkLayer   │  │
│  │  (EWMA +    │  │ (rarest-1st │  │  (async TCP,    │  │
│  │  eviction)  │  │  + endgame) │  │   BEP3 proto)   │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐                        │
│  │TrackerClient│  │   DHTNode   │                        │
│  │(HTTP + UDP) │  │ (Kademlia)  │                        │
│  └─────────────┘  └─────────────┘                        │
└──────────────┬───────────────────────────────────────────┘
               │
       ┌───────┴────────┬────────────────────┐
       │                │                    │
┌──────▼──────┐ ┌───────▼──────┐ ┌──────────▼─────────┐
│  ML Engine  │ │Security Layer│ │  Analytics / API   │
│             │ │              │ │                    │
│PeerSelector │ │ThreatDetector│ │MetricsCollector    │
│ (XGBoost)   │ │(IsolationF.) │ │NetworkGraphBuilder │
│             │ │              │ │                    │
│Download     │ │Reputation    │ │FastAPI + WebSocket │
│ Optimizer   │ │ System       │ │                    │
│             │ │(Redis-backed)│ │                    │
│Swarm        │ │              │ │                    │
│ Analyzer    │ │PieceValidator│ │                    │
│(K-Means)    │ │(SHA-1 +      │ │                    │
│             │ │ poison detect│ │                    │
└─────────────┘ └──────────────┘ └────────────────────┘
                                          │
                              ┌───────────▼──────────┐
                              │   React Dashboard    │
                              │  Overview / Peers /  │
                              │  Pieces / Swarm /    │
                              │  Security            │
                              └──────────────────────┘
```

---

## Features

### Core BitTorrent
- Full `.torrent` metadata parsing (single-file and multi-file modes)
- HTTP and UDP tracker announce / scrape (BEP 3, BEP 15)
- Kademlia DHT peer discovery (BEP 5) — bootstraps from public routers
- Async TCP peer connections with proper BEP 3 handshake and extension bytes
- Pipelined 16 KB block requests with reassembly
- SHA-1 piece verification on every received piece
- **Incremental disk writes** — pieces are written directly to pre-allocated output files as they arrive; no RAM buffering of the full torrent

### ML Layer
- **Peer Selector**: 10-feature XGBoost regression model (`latency`, `throughput`, `reliability`, `timeouts`, ...). Trains online on observed data once ≥50 samples are collected; retrains every hour. Falls back to composite EWMA score before training data exists. Model is persisted to `models/peer_selector.pkl`.
- **Download Optimizer**: Rarity-first piece ordering (availability-sorted), speed-weighted per peer; endgame mode activates at 95% completion and re-broadcasts remaining pieces to all connected peers.
- **Swarm Analyzer**: K-Means (k=5 default) on [latency, speed, reliability, timeouts]; classifies clusters as `fast / slow / unreliable / normal`; runs in background every 60 s.

### Security
- **Hash validation**: every piece checked against the SHA-1 from the `.torrent` info dict. Immediate retry on failure.
- **Poisoned torrent detection**: if ≥3 distinct peers all fail the same piece, it's flagged as poisoned.
- **Threat detection** (two-tier):
  - *Rule-based*: bad-data counter, upload spike detection (>2σ deviation), repeated timeout threshold
  - *Anomaly detection*: IsolationForest fitted on peer feature vectors once 100 observations are collected; contamination=0.05
- **Reputation system**: per-peer trust score 0–1, +0.02 on success, −0.05 on failure, decays toward 0.5 at 0.001/hour. Auto-blacklists peers below 0.15. Backed by Redis with 24-hour TTL.

### API & Dashboard
- REST endpoints for status, peers, pieces, swarm analysis, security events
- WebSocket endpoint pushing live telemetry at 1 Hz
- React SPA: speed sparkline (D3), piece bitmap, cluster bubble chart (D3 force layout), threat bar chart (D3)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Core | Python 3.11, `asyncio`, `bencodepy` |
| ML | `scikit-learn`, `xgboost`, `numpy`, `joblib` |
| Networking | `asyncio` streams + datagram, `aiohttp` |
| API | `FastAPI`, `uvicorn`, `websockets` |
| Security | `cryptography`, SHA-1 (stdlib `hashlib`) |
| Storage | `redis` (optional, falls back to in-memory) |
| Metrics | `prometheus_client` (optional) |
| CLI | `click`, `rich` |
| Dashboard | React 18, Vite, D3 v7, CSS custom properties |

---

## Project Structure

```
swyft/
├── cli.py                         # Entry point: download / analyze / serve / status
├── config.yaml                    # All tuneable parameters
├── requirements.txt
├── setup.py
├── pytest.ini
│
├── swyft/
│   ├── core/
│   │   ├── torrent_engine.py      # Orchestrator — ties all subsystems together
│   │   ├── peer_manager.py        # Peer pool with EWMA scoring and eviction
│   │   ├── piece_manager.py       # Piece state machine + rarest-first selection
│   │   ├── network_layer.py       # Async TCP, BEP 3 protocol, block pipelining
│   │   ├── tracker.py             # HTTP + UDP tracker client
│   │   └── dht.py                 # Kademlia DHT (BEP 5)
│   │
│   ├── ml/
│   │   ├── peer_selector.py       # XGBoost online learner + heuristic fallback
│   │   ├── download_optimizer.py  # Rarity-first + endgame mode
│   │   └── swarm_analyzer.py      # K-Means swarm clustering
│   │
│   ├── security/
│   │   ├── threat_detector.py     # IsolationForest + rule-based flagging
│   │   ├── reputation_system.py   # Trust scoring with Redis persistence
│   │   └── piece_validator.py     # SHA-1 validation + poison detection
│   │
│   ├── analytics/
│   │   ├── metrics_collector.py   # Speed, ETA, Prometheus, piece latency
│   │   └── network_graph.py       # D3-compatible swarm graph builder
│   │
│   └── api/
│       └── server.py              # FastAPI REST + WebSocket server
│
├── dashboard/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── hooks/useWebSocket.js
│   │   └── components/
│   │       ├── Overview.jsx       # Speed gauge, progress, sparkline, heatgrid
│   │       ├── PeersPage.jsx      # Sortable peer table with trust badges
│   │       ├── PiecesPage.jsx     # Full piece bitmap visualisation
│   │       ├── SwarmPage.jsx      # Cluster cards + D3 bubble chart
│   │       ├── SecurityPage.jsx   # Threat log + D3 bar chart
│   │       ├── SpeedChart.jsx     # D3 area/line sparkline
│   │       ├── ClusterBubble.jsx  # D3 force-directed cluster bubbles
│   │       └── Sidebar.jsx
│   └── ...
│
└── tests/
    ├── test_peer_manager.py
    ├── test_piece_manager.py
    ├── test_reputation.py
    └── test_threat_detector.py
```

---

## Installation

**Python ≥ 3.11 required.**

```bash
# Clone
git clone https://github.com/fromjyce/swyft.git
cd swyft

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# (Optional) editable install for the swyft package
pip install -e .
```

**Redis** (optional — reputation scores persist in-memory if Redis is unavailable):

```bash
# macOS
brew install redis && brew services start redis

# Docker
docker run -d -p 6379:6379 redis:7-alpine
```

---

## Usage

### CLI

```bash
# Download a torrent
python cli.py download path/to/file.torrent --output ./downloads

# Analyse a torrent file (parse metadata + tracker scrape, no download)
python cli.py analyze path/to/file.torrent

# Start the API + WebSocket server
python cli.py serve --port 8000

# Query a running instance
python cli.py status --api-url http://localhost:8000

# Verbose mode (debug logging)
python cli.py --verbose download file.torrent
```

### API Server

```bash
python cli.py serve
# → http://localhost:8000
# → http://localhost:8000/docs   (Swagger UI)
# → ws://localhost:8000/ws       (live WebSocket feed)
```

The WebSocket pushes a JSON frame every second:

```json
{
  "status":  { "name": "...", "progress": 0.72, "peers_active": 22, ... },
  "metrics": { "download_speed_mbps": 4.2, "eta_seconds": 180, ... },
  "swarm":   { "clusters": 5, "fast_clusters": 2, "cluster_details": [...] },
  "threats": { "bad_data": 2, "repeated_timeouts": 1, "anomalous_pattern": 0 }
}
```

### Dashboard

```bash
cd dashboard
npm install
npm run dev
# → http://localhost:5173
```

Requires the API server to be running on `http://localhost:8000`.

---

## Configuration

All parameters live in `config.yaml`. Key sections:

```yaml
torrent:
  max_peers: 50          # peer pool ceiling
  max_connections: 200   # TCP connection ceiling
  piece_size: 262144     # fallback (actual size from .torrent)
  connection_timeout: 30
  request_timeout: 60
  max_piece_retries: 3

ml:
  peer_selector:
    top_k: 15                 # peers chosen per download iteration
    min_training_samples: 50  # samples before XGBoost is trained
    retrain_interval: 3600    # seconds between retrains
  swarm_analyzer:
    n_clusters: 5
    update_interval: 60

security:
  trust_threshold: 0.45       # below this: pieces not trusted without verification
  blacklist_threshold: 0.15   # below this: peer is auto-banned
  anomaly_contamination: 0.05 # IsolationForest expected outlier ratio

redis:
  host: "localhost"
  port: 6379
  ttl_peer_reputation: 86400  # seconds (1 day)
```

---

## ML Layer

### Peer Selector

The `PeerSelector` collects a 10-dimensional feature vector for each peer after every download iteration:

```
[latency_ms, download_speed_mbps, upload_speed_mbps, reliability_score,
 pieces_received, pieces_failed, timeouts, seconds_since_active,
 is_connected, not_choking]
```

Labels are derived online: `label = pieces_received / (pieces_received + pieces_failed + timeouts)`.

An `XGBRegressor` is trained on a rolling buffer of up to 5,000 samples, once every hour (after at least 50 samples). Until then, the composite EWMA heuristic is used:

```
score = 0.4 × reliability + 0.3 × latency_norm + 0.3 × speed_norm − 0.1 × timeout_penalty
```

The trained model is saved to `models/peer_selector.pkl` and reloaded on startup.

### Download Optimizer

Pieces are scored per-peer:

```
piece_score = rarity_weight × (1 / availability) + speed_weight × min(speed_mbps / 10, 1.0)
```

Default weights: `rarity=0.6`, `speed=0.4`. Pieces assigned to other peers get a 0.5 penalty on rarity to reduce duplication.

**Endgame mode** activates at 95% completion: all remaining (missing + in-flight) pieces are broadcast to every available peer simultaneously to minimise stall time at the end.

### Swarm Analyzer

K-Means (k=5) runs on `[latency, speed, reliability, timeout_count]` every 60 seconds on connected peers. Clusters are labelled by threshold rules:

| Label | Criteria |
|---|---|
| `fast` | speed > 1 MB/s AND latency < 200 ms AND reliability > 0.8 |
| `unreliable` | reliability < 0.3 |
| `slow` | speed < 0.1 MB/s OR latency > 800 ms |
| `normal` | everything else |

---

## Security Layer

### Threat Detection (two-tier)

**Tier 1 — Rule-based (immediate):**
- `bad_data`: piece SHA-1 mismatch → severity scales with repetition
- `repeated_timeouts`: peer timeout count > 10
- `abnormal_upload`: current upload rate deviates > 2σ from peer's history

**Tier 2 — Anomaly detection (learned):**
- IsolationForest fitted on 7-dimensional feature vectors once 100 observations exist
- Refitted every 100 new samples (contamination=0.05)
- Outliers flagged as `anomalous_pattern` with an isolation score-derived severity

### Reputation System

```
score_new = score_old + 0.02   # on verified piece
score_new = score_old − 0.05   # on bad/failed piece

# Hourly decay toward 0.5 (neutral prior):
score = score + decay_rate * hours  # if score < 0.5
score = score − decay_rate * hours  # if score > 0.5
```

Scores below `blacklist_threshold` (default 0.15) trigger an automatic ban. Scores are stored in Redis under `swyft:rep:<peer_id_hex>` with a 24-hour TTL.

### Poisoned Torrent Detection

`PieceValidator` tracks which peers delivered a bad piece. If ≥3 distinct peers all fail the same piece index, that piece is flagged as **POISONED** (likely the `.torrent` file itself contains a corrupt/malicious hash, or the content is being selectively served incorrectly across the swarm).

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service liveness check |
| `POST` | `/torrent/add` | Start downloading `{ torrent_path, output_dir }` |
| `POST` | `/torrent/stop` | Stop active download |
| `GET` | `/torrent/status` | Download progress, speed, ETA |
| `GET` | `/peers` | All peers with metrics and trust level |
| `POST` | `/peers/action` | Ban or remove a peer `{ ip, port, action }` |
| `GET` | `/pieces` | Piece state bitmap |
| `GET` | `/swarm` | Cluster summary from swarm analyzer |
| `GET` | `/ml/peer-scores` | Current XGBoost scores for available peers |
| `GET` | `/security/threats` | Recent threat events + counts by type |
| `GET` | `/security/reputation` | All peer trust scores |
| `GET` | `/metrics` | Download metrics report |
| `WS` | `/ws` | Live JSON feed at 1 Hz |

Full interactive docs: `http://localhost:8000/docs`

---

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest
```

Test coverage:
- `test_peer_manager.py` — pool management, eviction, EWMA latency, composite score
- `test_piece_manager.py` — state machine, SHA-1 validation, rarest-first selection, availability tracking
- `test_reputation.py` — score updates, auto-blacklist, trust level labels, decay
- `test_threat_detector.py` — rule-based flagging, severity escalation, threat counting

---

## Design Decisions

**Why asyncio instead of libtorrent?**
Building on libtorrent is faster to ship but opaque — you can't hook ML decisions into the peer/piece scheduling loop. `asyncio` gives full control over connection management, piece dispatch timing, and data flow, which is necessary to integrate the ML and security layers meaningfully.

**Why XGBoost over a neural network?**
Peer scoring needs to work with very few samples (10–50 peers). XGBoost generalises well in this regime and trains in milliseconds, making online retraining viable. A neural network would require far more data and add unnecessary complexity.

**Why IsolationForest for anomaly detection?**
Peer behaviour is high-dimensional and the "normal" distribution is unknown ahead of time. IsolationForest is unsupervised, handles mixed-scale features well, and is cheap to fit and predict — important for a background security thread that shouldn't impact download throughput.

**Why incremental disk writes instead of buffering?**
Buffering the entire torrent in RAM is only viable for small files. Swyft pre-allocates output files and writes each piece at its correct byte offset as soon as it is verified, making multi-GB downloads practical without OOM risk.

**Why Redis for reputation?**
Peer reputation is valuable across sessions (you don't want to re-learn that a peer is malicious after restarting). Redis provides O(1) lookups, TTL-based expiry, and degrades gracefully to in-memory mode when unavailable.

---

## Contact

If you come across any issues, have suggestions for improvement, or want to discuss further enhancements, feel free to contact me at [jaya2004kra@gmail.com](mailto:jaya2004kra@gmail.com). Your feedback is greatly appreciated.

---

## License

All the code and resources in this repository are licensed under the GNU General Public License. You are free to use, modify, and distribute the code under the terms of this license. However, I do not take responsibility for the accuracy or reliability of the programs.
