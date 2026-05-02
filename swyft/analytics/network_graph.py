from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from swyft.core.peer_manager import PeerInfo


@dataclass
class GraphNode:
    id: str
    ip: str
    port: int
    latency_ms: float
    speed_mbps: float
    reliability: float
    trust_level: str


@dataclass
class GraphEdge:
    source: str
    target: str
    weight: float       # normalised bandwidth between nodes


@dataclass
class SwarmGraph:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nodes": [n.__dict__ for n in self.nodes],
            "edges": [e.__dict__ for e in self.edges],
        }


class NetworkGraphBuilder:
    """
    Constructs a D3-compatible graph of the peer swarm for
    visualisation in the dashboard.

    Nodes = peers, edges = estimated bandwidth similarity.
    """

    def build(self, peers: list["PeerInfo"]) -> SwarmGraph:
        nodes = [
            GraphNode(
                id=p.key,
                ip=p.ip,
                port=p.port,
                latency_ms=p.latency_ms if p.latency_ms != float("inf") else 9999.0,
                speed_mbps=p.download_speed_bps / 1e6,
                reliability=p.reliability_score,
                trust_level="neutral",
            )
            for p in peers if p.connected
        ]

        # Build edges between peers with similar performance characteristics
        edges: list[GraphEdge] = []
        for i, a in enumerate(peers):
            for b in peers[i+1:]:
                similarity = self._similarity(a, b)
                if similarity > 0.6:
                    edges.append(GraphEdge(source=a.key, target=b.key, weight=similarity))

        return SwarmGraph(nodes=nodes, edges=edges)

    @staticmethod
    def _similarity(a: "PeerInfo", b: "PeerInfo") -> float:
        if a.latency_ms == float("inf") or b.latency_ms == float("inf"):
            return 0.0
        lat_sim = 1.0 - abs(a.latency_ms - b.latency_ms) / max(a.latency_ms, b.latency_ms, 1)
        spd_sim = 1.0 - abs(a.download_speed_bps - b.download_speed_bps) / max(a.download_speed_bps, b.download_speed_bps, 1)
        rel_sim = 1.0 - abs(a.reliability_score - b.reliability_score)
        return (lat_sim + spd_sim + rel_sim) / 3.0
