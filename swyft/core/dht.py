from __future__ import annotations

import asyncio
import hashlib
import os
import random
import socket
import struct
import time
from collections import defaultdict
from typing import Optional

import bencodepy
from loguru import logger

BOOTSTRAP_NODES = [
    ("router.bittorrent.com", 6881),
    ("dht.transmissionbt.com", 6881),
    ("router.utorrent.com", 6881),
]

K = 8           # Kademlia bucket size
ALPHA = 3       # Kademlia concurrency


def generate_node_id() -> bytes:
    return os.urandom(20)


def xor_distance(a: bytes, b: bytes) -> int:
    return int.from_bytes(a, "big") ^ int.from_bytes(b, "big")


def compact_peer_info(ip: str, port: int) -> bytes:
    return socket.inet_aton(ip) + struct.pack(">H", port)


class KBucket:
    """A single bucket in the Kademlia routing table."""

    def __init__(self):
        self.nodes: list[dict] = []  # {"id": bytes, "ip": str, "port": int, "last_seen": float}
        self.last_changed = time.time()

    def add(self, node: dict) -> bool:
        node_id = node["id"]
        for existing in self.nodes:
            if existing["id"] == node_id:
                existing["last_seen"] = time.time()
                return True
        if len(self.nodes) < K:
            self.nodes.append({**node, "last_seen": time.time()})
            self.last_changed = time.time()
            return True
        return False

    def remove(self, node_id: bytes):
        self.nodes = [n for n in self.nodes if n["id"] != node_id]

    def is_full(self) -> bool:
        return len(self.nodes) >= K


class RoutingTable:
    def __init__(self, local_id: bytes):
        self.local_id = local_id
        self.buckets: list[KBucket] = [KBucket() for _ in range(160)]

    def _bucket_index(self, node_id: bytes) -> int:
        distance = xor_distance(self.local_id, node_id)
        if distance == 0:
            return 0
        return 159 - distance.bit_length() + 1

    def add_node(self, node: dict):
        idx = self._bucket_index(node["id"])
        self.buckets[idx].add(node)

    def get_closest(self, target: bytes, n: int = K) -> list[dict]:
        all_nodes = [n for bucket in self.buckets for n in bucket.nodes]
        all_nodes.sort(key=lambda nd: xor_distance(nd["id"], target))
        return all_nodes[:n]

    def total_nodes(self) -> int:
        return sum(len(b.nodes) for b in self.buckets)


class DHTNode:
    """
    Kademlia-based DHT node implementing BEP 5.
    Supports: ping, find_node, get_peers, announce_peer.
    """

    def __init__(self, config: dict):
        self.config = config
        self.node_id = generate_node_id()
        self.port: int = config["dht"]["port"]
        self.routing_table = RoutingTable(self.node_id)
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._pending: dict[bytes, asyncio.Future] = {}
        self._peer_store: dict[bytes, list[dict]] = defaultdict(list)  # info_hash -> peers
        self._running = False

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def start(self, info_hash: Optional[bytes] = None):
        self._running = True
        loop = asyncio.get_event_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _DHTProtocol(self),
            local_addr=("0.0.0.0", self.port),
        )
        logger.info(f"[DHT] Node started on port {self.port}, id={self.node_id.hex()[:8]}...")
        await self._bootstrap()
        if info_hash:
            asyncio.create_task(self._find_peers_loop(info_hash))

    async def stop(self):
        self._running = False
        if self._transport:
            self._transport.close()

    # ------------------------------------------------------------------ #
    # Bootstrap                                                            #
    # ------------------------------------------------------------------ #

    async def _bootstrap(self):
        nodes = self.config["dht"].get("bootstrap_nodes", BOOTSTRAP_NODES)
        tasks = [self._ping(host, port) for host, port in nodes]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"[DHT] Bootstrap complete, known nodes: {self.routing_table.total_nodes()}")

    # ------------------------------------------------------------------ #
    # get_peers loop                                                       #
    # ------------------------------------------------------------------ #

    async def _find_peers_loop(self, info_hash: bytes):
        while self._running:
            peers = await self.get_peers(info_hash)
            if peers:
                logger.info(f"[DHT] Found {len(peers)} peers via DHT")
            await asyncio.sleep(60)

    async def get_peers(self, info_hash: bytes) -> list[dict]:
        closest = self.routing_table.get_closest(info_hash, K)
        queried: set[bytes] = set()
        found: list[dict] = []

        for node in closest[:ALPHA]:
            result = await self._query_get_peers(node, info_hash)
            queried.add(node["id"])
            if result:
                found.extend(result.get("peers", []))

        return found

    # ------------------------------------------------------------------ #
    # Low-level RPC                                                        #
    # ------------------------------------------------------------------ #

    async def _ping(self, host: str, port: int) -> Optional[dict]:
        tid = os.urandom(2)
        msg = bencodepy.encode({
            b"t": tid,
            b"y": b"q",
            b"q": b"ping",
            b"a": {b"id": self.node_id},
        })
        return await self._send_query(host, port, tid, msg)

    async def _query_find_node(self, node: dict, target: bytes) -> Optional[dict]:
        tid = os.urandom(2)
        msg = bencodepy.encode({
            b"t": tid,
            b"y": b"q",
            b"q": b"find_node",
            b"a": {b"id": self.node_id, b"target": target},
        })
        return await self._send_query(node["ip"], node["port"], tid, msg)

    async def _query_get_peers(self, node: dict, info_hash: bytes) -> Optional[dict]:
        tid = os.urandom(2)
        msg = bencodepy.encode({
            b"t": tid,
            b"y": b"q",
            b"q": b"get_peers",
            b"a": {b"id": self.node_id, b"info_hash": info_hash},
        })
        return await self._send_query(node["ip"], node["port"], tid, msg)

    async def _send_query(self, host: str, port: int, tid: bytes, msg: bytes) -> Optional[dict]:
        if not self._transport:
            return None
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[tid] = fut
        try:
            self._transport.sendto(msg, (host, port))
            return await asyncio.wait_for(fut, timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            return None
        finally:
            self._pending.pop(tid, None)

    # ------------------------------------------------------------------ #
    # Incoming message handler (called by protocol)                       #
    # ------------------------------------------------------------------ #

    def _handle_message(self, data: bytes, addr: tuple[str, int]):
        try:
            msg = bencodepy.decode(data)
        except Exception:
            return

        tid = msg.get(b"t", b"")
        msg_type = msg.get(b"y", b"")

        if msg_type == b"r":
            # Response to our query
            fut = self._pending.get(tid)
            if fut and not fut.done():
                r = msg.get(b"r", {})
                # Register node
                sender_id = r.get(b"id")
                if sender_id:
                    self.routing_table.add_node({"id": sender_id, "ip": addr[0], "port": addr[1]})
                # Parse peers if present
                result: dict = {}
                if b"values" in r:
                    peers = []
                    for raw_peer in r[b"values"]:
                        if len(raw_peer) == 6:
                            ip = socket.inet_ntoa(raw_peer[:4])
                            port = struct.unpack(">H", raw_peer[4:6])[0]
                            peers.append({"ip": ip, "port": port})
                    result["peers"] = peers
                if b"nodes" in r:
                    result["nodes"] = r[b"nodes"]
                fut.set_result(result)

        elif msg_type == b"q":
            # Incoming query — respond
            asyncio.create_task(self._handle_query(msg, addr))

    async def _handle_query(self, msg: dict, addr: tuple[str, int]):
        if not self._transport:
            return
        tid = msg[b"t"]
        q = msg.get(b"q", b"")
        a = msg.get(b"a", {})
        sender_id = a.get(b"id", b"")

        self.routing_table.add_node({"id": sender_id, "ip": addr[0], "port": addr[1]})

        if q == b"ping":
            resp = {b"t": tid, b"y": b"r", b"r": {b"id": self.node_id}}
        elif q == b"find_node":
            target = a.get(b"target", b"")
            closest = self.routing_table.get_closest(target)
            resp = {b"t": tid, b"y": b"r", b"r": {b"id": self.node_id, b"nodes": b""}}
        elif q == b"get_peers":
            info_hash = a.get(b"info_hash", b"")
            stored = self._peer_store.get(info_hash, [])
            token = os.urandom(4)
            if stored:
                values = [compact_peer_info(p["ip"], p["port"]) for p in stored[:30]]
                resp = {b"t": tid, b"y": b"r", b"r": {b"id": self.node_id, b"token": token, b"values": values}}
            else:
                closest = self.routing_table.get_closest(info_hash)
                resp = {b"t": tid, b"y": b"r", b"r": {b"id": self.node_id, b"token": token, b"nodes": b""}}
        elif q == b"announce_peer":
            info_hash = a.get(b"info_hash", b"")
            peer_port = a.get(b"port", addr[1])
            self._peer_store[info_hash].append({"ip": addr[0], "port": peer_port})
            resp = {b"t": tid, b"y": b"r", b"r": {b"id": self.node_id}}
        else:
            return

        self._transport.sendto(bencodepy.encode(resp), addr)


class _DHTProtocol(asyncio.DatagramProtocol):
    def __init__(self, node: DHTNode):
        self.node = node

    def datagram_received(self, data: bytes, addr):
        self.node._handle_message(data, addr)

    def error_received(self, exc):
        logger.debug(f"[DHT] Protocol error: {exc}")
