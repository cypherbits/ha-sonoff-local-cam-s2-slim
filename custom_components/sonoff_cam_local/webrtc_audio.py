"""Send audio to the camera's speaker over its local WebRTC endpoint.

The camera (an Amazon Kinesis Video Streams / ``myKvsVideoStream`` peer) exposes
a **local** WebRTC endpoint signalled over its own JSON-RPC service. Its web
console only negotiates a receive audio track (``recvonly``), but the peer
accepts a ``sendrecv`` audio track carrying **PCMA/8000** (G.711 A-law) - the
same mechanism the eWeLink app uses for its two-way "Talk" button.

This module reproduces that: it opens a WebRTC session through ``Webrtc.SetConfig``
/ ``LiveStream.SetConfig`` and streams PCM frames (decoded on the fly, so live
radio works), which :mod:`aiortc` encodes to PCMA/8000.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
import warnings
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

import av

with warnings.catch_warnings():
    # aiortc pulls in google-crc32c, which warns when its C extension is missing.
    warnings.filterwarnings("ignore", message=".*pure python implementation.*")
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.mediastreams import MediaStreamTrack

_LOGGER = logging.getLogger(__name__)

WEBRTC_SET_CONFIG = "Webrtc.SetConfig"
LIVE_STREAM_SET_CONFIG = "LiveStream.SetConfig"

RpcCall = Callable[[str, dict[str, Any] | None], Coroutine[Any, Any, dict[str, Any]]]

#: PCMA/8000 is a 20 ms frame of 160 samples; decoded audio is resampled to 48 kHz.
_FRAME_SAMPLES = 160
_SAMPLE_RATE = 8000
_TARGET_RATE = 48000


def _silence() -> av.AudioFrame:
    frame = av.AudioFrame(format="s16", layout="mono", samples=_FRAME_SAMPLES)
    frame.sample_rate = _SAMPLE_RATE
    return frame


class AudioSourceStreamer:
    """Blocking decoder for a URL / file, yielding mono s16 48 kHz frames."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._container: av.container.InputContainer | None = None
        self._closed = False

    def frames(self) -> Iterator[av.AudioFrame]:
        """Yield resampled frames until the source ends or :meth:`close` is called."""
        container = av.open(self._source)
        self._container = container
        try:
            if not container.streams.audio:
                raise ValueError("media contains no audio stream")
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="s16", layout="mono", rate=_TARGET_RATE)
            for frame in container.decode(stream):
                if self._closed:
                    break
                for resampled in resampler.resample(frame):
                    yield resampled
            if not self._closed:
                for resampled in resampler.resample(None):
                    yield resampled
        finally:
            # Closed here (decoder thread), never from the event loop: closing a
            # container while another thread is inside decode() can crash ffmpeg.
            self._container = None
            with contextlib.suppress(Exception):
                container.close()

    def close(self) -> None:
        """Ask the decoder to stop after the current frame."""
        self._closed = True


class CameraAudioTrack(MediaStreamTrack):
    """An audio track fed from a queue; outputs silence while idle."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[av.AudioFrame | None] = asyncio.Queue()
        self._pts = 0
        self._ended = False

    def push(self, frame: av.AudioFrame) -> None:
        """Queue a frame for transmission (must run on the event loop)."""
        self._queue.put_nowait(frame)

    def end(self) -> None:
        """Signal that no more audio will be queued."""
        self._ended = True

    async def recv(self) -> av.AudioFrame:
        """Return the next queued frame, or a silence frame when idle.

        The producer paces the queue in real time, so no extra sleeping is done
        here - that would halve the effective bitrate on live sources.
        """
        frame: av.AudioFrame | None = None
        if not (self._ended and self._queue.empty()):
            try:
                frame = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                frame = None
        if frame is None:
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
        self._streamer: AudioSourceStreamer | None = None
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

    async def stream_source(self, source: str) -> None:
        """Decode ``source`` (URL or file) and stream it in real time.

        Handles finite files and infinite live streams (radio): the decoder runs
        in a worker thread and paces frames against the wall clock, so nothing is
        ever buffered in full.
        """
        if self._track is None:
            raise RuntimeError("session is not started")

        loop = asyncio.get_running_loop()
        track = self._track
        streamer = AudioSourceStreamer(source)
        self._streamer = streamer

        def _run() -> None:
            started = time.monotonic()
            audio_time = 0.0
            frames = streamer.frames()
            try:
                for frame in frames:
                    if self._closed:
                        break
                    loop.call_soon_threadsafe(track.push, frame)
                    audio_time += frame.samples / frame.sample_rate
                    delay = audio_time - (time.monotonic() - started)
                    if delay > 0:
                        time.sleep(delay)
                    else:
                        # We are behind (live source): resync the clock.
                        started = time.monotonic() - audio_time
            finally:
                # Close the generator here so ffmpeg is torn down in this thread.
                frames.close()
                loop.call_soon_threadsafe(track.end)

        await loop.run_in_executor(None, _run)

    async def close(self) -> None:
        """Tear down the session and stop any decoder."""
        self._closed = True
        if self._streamer is not None:
            self._streamer.close()
            self._streamer = None
        if self._track is not None:
            self._track.end()
        if self._pc is not None:
            await self._pc.close()
            self._pc = None
