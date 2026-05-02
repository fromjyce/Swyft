from __future__ import annotations

import asyncio
import random
import socket
import struct
import urllib.parse
from typing import Optional

import aiohttp
import bencodepy
from loguru import logger


class TrackerClient:
    """Handles HTTP and UDP tracker announces."""

    def __init__(self, config: dict):
        self.config = config

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def announce(
        self,
        tracker_url: str,
        info_hash: bytes,
        peer_id: bytes,
        port: int,
        uploaded: int,
        downloaded: int,
        left: int,
        event: str = "started",
    ) -> list[dict]:
        if tracker_url.startswith("http"):
            return await self._announce_http(
                tracker_url, info_hash, peer_id, port,
                uploaded, downloaded, left, event
            )
        elif tracker_url.startswith("udp"):
            return await self._announce_udp(
                tracker_url, info_hash, peer_id, port,
                uploaded, downloaded, left, event
            )
        else:
            logger.warning(f"[Tracker] Unsupported tracker scheme: {tracker_url}")
            return []

    async def scrape(self, tracker_url: str, info_hash: bytes) -> Optional[dict]:
        if not tracker_url.startswith("http"):
            return None
        scrape_url = tracker_url.replace("announce", "scrape")
        params = {"info_hash": info_hash}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(scrape_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = bencodepy.decode(await resp.read())
                    files = data.get(b"files", {})
                    if info_hash in files:
                        f = files[info_hash]
                        return {
                            "complete": f.get(b"complete", 0),
                            "incomplete": f.get(b"incomplete", 0),
                            "downloaded": f.get(b"downloaded", 0),
                        }
        except Exception as e:
            logger.debug(f"[Tracker] Scrape failed: {e}")
        return None

    # ------------------------------------------------------------------ #
    # HTTP tracker                                                         #
    # ------------------------------------------------------------------ #

    async def _announce_http(
        self,
        url: str,
        info_hash: bytes,
        peer_id: bytes,
        port: int,
        uploaded: int,
        downloaded: int,
        left: int,
        event: str,
    ) -> list[dict]:
        params = {
            "info_hash": info_hash,
            "peer_id": peer_id,
            "port": str(port),
            "uploaded": str(uploaded),
            "downloaded": str(downloaded),
            "left": str(left),
            "compact": "1",
            "event": event,
            "numwant": str(self.config["tracker"]["num_want"]),
        }
        full_url = url + "?" + urllib.parse.urlencode(params)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    body = await resp.read()
            decoded = bencodepy.decode(body)
            if b"failure reason" in decoded:
                logger.warning(f"[Tracker] Failure: {decoded[b'failure reason'].decode()}")
                return []
            return self._parse_peers(decoded.get(b"peers", b""))
        except Exception as e:
            logger.warning(f"[Tracker] HTTP announce failed: {e}")
            return []

    def _parse_peers(self, raw: bytes) -> list[dict]:
        """Parse compact peer list (6 bytes per peer: 4 IP + 2 port)."""
        peers = []
        for i in range(0, len(raw) - 5, 6):
            ip = socket.inet_ntoa(raw[i:i+4])
            port = struct.unpack(">H", raw[i+4:i+6])[0]
            if port > 0:
                peers.append({"ip": ip, "port": port})
        logger.info(f"[Tracker] Got {len(peers)} peers")
        return peers

    # ------------------------------------------------------------------ #
    # UDP tracker (RFC 8445 / BEP 15)                                     #
    # ------------------------------------------------------------------ #

    async def _announce_udp(
        self,
        url: str,
        info_hash: bytes,
        peer_id: bytes,
        port: int,
        uploaded: int,
        downloaded: int,
        left: int,
        event: str,
    ) -> list[dict]:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        tracker_port = parsed.port or 80

        loop = asyncio.get_event_loop()
        try:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: _UDPTrackerProtocol(),
                remote_addr=(host, tracker_port),
            )
            prot: _UDPTrackerProtocol = protocol

            # Step 1: Connect
            transaction_id = random.randint(0, 0xFFFFFFFF)
            connect_req = struct.pack(">QII", 0x41727101980, 0, transaction_id)
            transport.sendto(connect_req)

            conn_resp = await asyncio.wait_for(prot.recv(), timeout=10)
            if len(conn_resp) < 16 or struct.unpack(">II", conn_resp[:8]) != (0, transaction_id):
                return []
            connection_id = struct.unpack(">Q", conn_resp[8:16])[0]

            # Step 2: Announce
            event_map = {"started": 2, "completed": 1, "stopped": 3, "": 0}
            ev_code = event_map.get(event, 0)
            transaction_id = random.randint(0, 0xFFFFFFFF)
            ann_req = struct.pack(
                ">QII20s20sQQQIIIiH",
                connection_id, 1, transaction_id,
                info_hash, peer_id,
                downloaded, left, uploaded,
                ev_code, 0, 0, -1, port,
            )
            transport.sendto(ann_req)

            ann_resp = await asyncio.wait_for(prot.recv(), timeout=10)
            transport.close()

            if len(ann_resp) < 20:
                return []

            raw_peers = ann_resp[20:]
            return self._parse_peers(raw_peers)

        except Exception as e:
            logger.debug(f"[Tracker] UDP announce failed: {e}")
            return []


class _UDPTrackerProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    def datagram_received(self, data: bytes, addr):
        self._queue.put_nowait(data)

    async def recv(self) -> bytes:
        return await self._queue.get()
