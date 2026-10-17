"""Send audio to the camera's speaker over its local WebRTC endpoint.

The camera (an Amazon Kinesis Video Streams / ``myKvsVideoStream`` peer) exposes
a **local** WebRTC endpoint signalled over its own JSON-RPC service. Its web
console only negotiates a receive audio track (``recvonly``), but the peer
accepts a ``sendrecv`` audio track carrying **PCMA/8000** (G.711 A-law) - the
same mechanism the eWeLink app uses for its two-way "Talk" button.

This module reproduces that: it opens a WebRTC session through ``Webrtc.SetConfig``
/ ``LiveStream.SetConfig`` and streams PCM frames, which :mod:`aiortc` encodes
to PCMA/8000.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import av
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack

_LOGGER = logging.getLogger(__name__)

WEBRTC_SET_CONFIG = "Webrtc.SetConfig"
LIVE_STREAM_SET_CONFIG = "LiveStream.SetConfig"

RpcCall = Callable[[str, dict[str, Any] | None], Coroutine[Any, Any, dict[str, Any]]]

#: PCMA/8000 is a 20 ms frame of 160 samples.
_FRAME_SAMPLES = 160
_SAMPLE_RATE = 8000


def _silence() -> av.AudioFrame:
    frame = av.AudioFrame(format="s16", layout="mono", samples=_FRAME_SAMPLES)
    frame.sample_rate = _SAMPLE_RATE
    return frame


class CameraAudioTrack(MediaStreamTrack):
    """An audio track fed from a queue; outputs silence while idle."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[av.AudioFrame | None] = asyncio.Queue()
        self._pts = 0
        self._ended = False

    def push(self, frame: av.AudioFrame) -> None:
        """Queue a frame for transmission."""
        self._queue.put_nowait(frame)

    def end(self) -> None:
        """Signal that no more audio will be queued."""
        self._ended = True

    async def recv(self) -> av.AudioFrame:
        """Return the next frame, or a silence frame while the queue is empty."""
        frame: av.AudioFrame | None = None
        if not self._ended:
            try:
                frame = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                frame = None
        if frame is None:
            # Keep the stream alive with (paced) silence.
            await asyncio.sleep(_FRAME_SAMPLES / _SAMPLE_RATE)
            frame = _silence()
        frame.pts = self._pts
        self._pts += frame.samples
        return frame


class CameraAudioSession:
    """One WebRTC audio session towards the camera speaker."""

    def __init__(self, rpc: RpcCall) -> None:
        self._rpc = rpc
        self._pc: RTCPeerConnection | None = None
        self._track: CameraAudioTrack | None = None
        self._session_id = f"local_{random.getrandbits(48):x}"
        self._closed = False

    async def start(self) -> None:
        """Negotiate the WebRTC session and wait for it to connect."""
        pc = RTCPeerConnection()
        pc.addTransceiver("video", direction="recvonly")
        track = CameraAudioTrack()
        pc.addTrack(track)

        @pc.on("icecandidate")
        async def _on_ice(candidate: Any) -> None:
            if candidate is None:
                return
            try:
                await self._rpc(
                    WEBRTC_SET_CONFIG,
                    {
                        "sessionId": self._session_id,
                        "msgType": "ice",
                        "data": {
                            "candidate": candidate.candidate,
                            "sdpMid": candidate.sdpMid or "0",
                            "sdpMLineIndex": candidate.sdpMLineIndex or 0,
                        },
                    },
                )
            except Exception as err:
                _LOGGER.debug("WebRTC ICE send failed: %s", err)

        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        assert pc.localDescription is not None

        result = await self._rpc(
            WEBRTC_SET_CONFIG,
            {
                "sessionId": self._session_id,
                "msgType": "sdp",
                "data": {"type": "offer", "sdp": pc.localDescription.sdp},
            },
        )
        data = result.get("data") or {}
        if data.get("type") != "answer" or not data.get("sdp"):
            await pc.close()
            raise RuntimeError("camera did not return a WebRTC answer")

        await pc.setRemoteDescription(RTCSessionDescription(sdp=data["sdp"], type="answer"))
        try:
            await self._rpc(
                LIVE_STREAM_SET_CONFIG,
                {"sessionId": self._session_id, "action": "playMedia"},
            )
        except Exception as err:
            _LOGGER.debug("playMedia failed: %s", err)

        self._pc = pc
        self._track = track

        for _ in range(40):
            if pc.connectionState in ("connected", "failed", "closed"):
                break
            await asyncio.sleep(0.25)
        if pc.connectionState != "connected":
            _LOGGER.warning("WebRTC audio session state is %s", pc.connectionState)

    async def stream(self, frames: AsyncIterator[av.AudioFrame]) -> None:
        """Send frames in real time until the iterator is exhausted."""
        if self._track is None:
            raise RuntimeError("session is not started")
        async for frame in frames:
            if self._closed:
                return
            self._track.push(frame)
            await asyncio.sleep(frame.samples / frame.sample_rate)

    async def close(self) -> None:
        """Tear down the session."""
        self._closed = True
        if self._track is not None:
            self._track.end()
        if self._pc is not None:
            await self._pc.close()
            self._pc = None


def decode_audio(data: bytes) -> list[av.AudioFrame]:
    """Decode arbitrary audio bytes into mono s16 48 kHz frames (blocking)."""
    frames: list[av.AudioFrame] = []
    container = av.open(_bytes_io(data))
    try:
        if not container.streams.audio:
            raise ValueError("media contains no audio stream")
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                frames.append(resampled)
        for resampled in resampler.resample(None):
            frames.append(resampled)
    finally:
        container.close()
    return frames


def _bytes_io(data: bytes) -> Any:
    import io

    return io.BytesIO(data)
