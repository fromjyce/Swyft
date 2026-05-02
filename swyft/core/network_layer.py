from __future__ import annotations

import asyncio
import struct
import time
from typing import Optional

from loguru import logger

from swyft.core.peer_manager import PeerInfo


# BitTorrent message IDs
MSG_CHOKE = 0
MSG_UNCHOKE = 1
MSG_INTERESTED = 2
MSG_NOT_INTERESTED = 3
MSG_HAVE = 4
MSG_BITFIELD = 5
MSG_REQUEST = 6
MSG_PIECE = 7
MSG_CANCEL = 8
MSG_PORT = 9  # DHT port

HANDSHAKE_PSTR = b"BitTorrent protocol"
HANDSHAKE_PSTRLEN = len(HANDSHAKE_PSTR)

BLOCK_SIZE = 16384  # 16 KB — standard BitTorrent block size


class BitTorrentConnection:
    """Wraps a single TCP connection to a remote peer."""

    def __init__(
        self,
        peer: PeerInfo,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        info_hash: bytes,
        peer_id: bytes,
    ):
        self.peer = peer
        self.reader = reader
        self.writer = writer
        self.info_hash = info_hash
        self.peer_id = peer_id
        self._closed = False

    # ------------------------------------------------------------------ #
    # Handshake                                                            #
    # ------------------------------------------------------------------ #

    async def do_handshake(self) -> bool:
        try:
            payload = (
                bytes([HANDSHAKE_PSTRLEN])
                + HANDSHAKE_PSTR
                + b"\x00" * 8          # reserved (extension bytes)
                + self.info_hash
                + self.peer_id
            )
            self.writer.write(payload)
            await self.writer.drain()

            response = await asyncio.wait_for(self.reader.readexactly(68), timeout=10)
            remote_info_hash = response[28:48]
            remote_peer_id = response[48:68]

            if remote_info_hash != self.info_hash:
                logger.debug(f"[Net] Handshake failed with {self.peer.ip}: info_hash mismatch")
                return False

            self.peer.peer_id = remote_peer_id
            self.peer.handshaked = True
            logger.debug(f"[Net] Handshake OK with {self.peer.ip}")
            return True
        except (asyncio.TimeoutError, ConnectionResetError, asyncio.IncompleteReadError) as e:
            logger.debug(f"[Net] Handshake error {self.peer.ip}: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Message I/O                                                          #
    # ------------------------------------------------------------------ #

    async def send_message(self, msg_id: int, payload: bytes = b""):
        length = 1 + len(payload)
        msg = struct.pack(">I", length) + bytes([msg_id]) + payload
        self.writer.write(msg)
        await self.writer.drain()

    async def recv_message(self, timeout: float = 60.0) -> Optional[tuple[int, bytes]]:
        try:
            raw_len = await asyncio.wait_for(self.reader.readexactly(4), timeout=timeout)
            length = struct.unpack(">I", raw_len)[0]
            if length == 0:
                return None, b""  # keep-alive
            raw = await asyncio.wait_for(self.reader.readexactly(length), timeout=timeout)
            return raw[0], raw[1:]
        except asyncio.TimeoutError:
            return None, b""
        except (asyncio.IncompleteReadError, ConnectionResetError):
            return -1, b""

    # ------------------------------------------------------------------ #
    # High-level protocol messages                                         #
    # ------------------------------------------------------------------ #

    async def send_interested(self):
        await self.send_message(MSG_INTERESTED)
        self.peer.am_interested = True

    async def send_not_interested(self):
        await self.send_message(MSG_NOT_INTERESTED)
        self.peer.am_interested = False

    async def send_unchoke(self):
        await self.send_message(MSG_UNCHOKE)
        self.peer.am_choking = False

    async def send_have(self, piece_index: int):
        await self.send_message(MSG_HAVE, struct.pack(">I", piece_index))

    async def send_request(self, piece_index: int, offset: int, block_length: int):
        payload = struct.pack(">III", piece_index, offset, block_length)
        await self.send_message(MSG_REQUEST, payload)

    async def request_piece_blocks(self, piece_index: int, piece_length: int) -> Optional[bytes]:
        """Request all blocks of a piece and assemble them."""
        blocks: dict[int, bytes] = {}
        remaining = piece_length
        offset = 0

        # Pipeline requests
        while remaining > 0:
            block_len = min(BLOCK_SIZE, remaining)
            await self.send_request(piece_index, offset, block_len)
            remaining -= block_len
            offset += block_len

        # Receive responses
        expected_blocks = (piece_length + BLOCK_SIZE - 1) // BLOCK_SIZE
        deadline = time.monotonic() + 30.0

        while len(blocks) < expected_blocks:
            if time.monotonic() > deadline:
                logger.debug(f"[Net] Timeout collecting blocks for piece {piece_index}")
                return None
            msg_id, payload = await self.recv_message(timeout=10.0)
            if msg_id == MSG_PIECE and len(payload) >= 8:
                idx = struct.unpack(">I", payload[0:4])[0]
                off = struct.unpack(">I", payload[4:8])[0]
                data = payload[8:]
                if idx == piece_index:
                    blocks[off] = data

        return b"".join(blocks[off] for off in sorted(blocks))

    async def close(self):
        if not self._closed:
            self._closed = True
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass


class NetworkLayer:
    def __init__(self, config: dict):
        self.config = config
        self._connections: dict[str, BitTorrentConnection] = {}

    async def connect(
        self, peer: PeerInfo, info_hash: bytes, local_peer_id: bytes
    ) -> Optional[BitTorrentConnection]:
        timeout = self.config["torrent"]["connection_timeout"]
        try:
            t0 = time.monotonic()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(peer.ip, peer.port),
                timeout=timeout,
            )
            latency_ms = (time.monotonic() - t0) * 1000

            conn = BitTorrentConnection(peer, reader, writer, info_hash, local_peer_id)
            if await conn.do_handshake():
                peer.connected = True
                peer.latency_ms = latency_ms
                self._connections[peer.key] = conn
                return conn

            await conn.close()
            return None
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError) as e:
            logger.debug(f"[Net] Cannot connect to {peer.ip}:{peer.port}: {e}")
            return None

    async def request_piece(
        self,
        peer: PeerInfo,
        piece_index: int,
        piece_length: int,
        timeout: float = 30.0,
    ) -> Optional[bytes]:
        conn = self._connections.get(peer.key)
        if conn is None:
            return None
        try:
            return await asyncio.wait_for(
                conn.request_piece_blocks(piece_index, piece_length),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return None

    async def close_all(self):
        for conn in list(self._connections.values()):
            await conn.close()
        self._connections.clear()

    def connection_count(self) -> int:
        return len(self._connections)
