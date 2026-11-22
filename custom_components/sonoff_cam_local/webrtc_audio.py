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
import subprocess
import sys
import time
import warnings
from collections.abc import Callable, Coroutine, Iterator
from fractions import Fraction
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
_TARGET_RATE = 48000
_TARGET_FRAME_SAMPLES = 960  # 20 ms at 48 kHz
_SAMPLE_WIDTH = 2  # s16 mono

#: Run the decoder in a child process. PyAV/FFmpeg crashes then kill only the
#: decoder, not Home Assistant itself.
_DECODER_SCRIPT = r"""
import sys
import av

source = sys.argv[1]
container = av.open(source)
try:
    if not container.streams.audio:
        raise SystemExit("media contains no audio stream")
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
    out = sys.stdout.buffer
    for frame in container.decode(stream):
        for resampled in resampler.resample(frame):
            out.write(bytes(resampled.planes[0])[: resampled.samples * 2])
            out.flush()
    for resampled in resampler.resample(None):
        out.write(bytes(resampled.planes[0])[: resampled.samples * 2])
        out.flush()
finally:
    container.close()
"""


def _silence() -> av.AudioFrame:
    frame = av.AudioFrame(
        format="s16", layout="mono", samples=_TARGET_FRAME_SAMPLES
    )
    frame.sample_rate = _TARGET_RATE
    frame.time_base = Fraction(1, _TARGET_RATE)
    return frame


def _frame_from_bytes(data: bytes) -> av.AudioFrame:
    frame = av.AudioFrame(
        format="s16", layout="mono", samples=_TARGET_FRAME_SAMPLES
    )
    frame.sample_rate = _TARGET_RATE
    frame.time_base = Fraction(1, _TARGET_RATE)
    frame.planes[0].update(data)
    return frame


class AudioSourceStreamer:
    """Decode a URL / file in a child process, yielding 20 ms s16 48 kHz frames."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._process: subprocess.Popen[bytes] | None = None
        self._closed = False

    def frames(self) -> Iterator[av.AudioFrame]:
        """Yield resampled frames until the source ends or :meth:`close` is called."""
        frame_bytes = _TARGET_FRAME_SAMPLES * _SAMPLE_WIDTH
        process = subprocess.Popen(
            [sys.executable, "-c", _DECODER_SCRIPT, self._source],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._process = process
        stdout = process.stdout
        assert stdout is not None
        buffer = bytearray()
        try:
            while not self._closed:
                chunk = stdout.read(4096)
                if not chunk:
                    break
                buffer.extend(chunk)
                while len(buffer) >= frame_bytes:
                    data = bytes(buffer[:frame_bytes])
                    del buffer[:frame_bytes]
                    yield _frame_from_bytes(data)
            if not self._closed and buffer:
                data = bytes(buffer) + b"\x00" * (frame_bytes - len(buffer))
                yield _frame_from_bytes(data)
        finally:
            self._process = None
            closed_by_us = self._closed
            with contextlib.suppress(Exception):
                stdout.close()
            if process.poll() is None:
                if closed_by_us:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    with contextlib.suppress(Exception):
                        process.wait(timeout=2)
            if process.returncode not in (0, None) and not closed_by_us:
                _LOGGER.warning(
                    "Audio decoder for %s exited with code %s",
                    self._source,
                    process.returncode,
                )

    def close(self) -> None:
        """Ask the decoder to stop after the current frame."""
        self._closed = True
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()


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
        for normal playback. When playback has ended, silence is paced at 20 ms
        so the sender cannot spin at full speed.
        """
        frame: av.AudioFrame | None = None
        if self._ended and self._queue.empty():
            await asyncio.sleep(_TARGET_FRAME_SAMPLES / _TARGET_RATE)
        else:
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
        track = CameraAudioTrack()
        try:
            pc.addTransceiver("video", direction="recvonly")
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
                raise RuntimeError("camera did not return a WebRTC answer")

            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=data["sdp"], type="answer")
            )
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
            if pc.connectionState in ("failed", "closed"):
                raise RuntimeError(f"WebRTC session state is {pc.connectionState}")
            if pc.connectionState != "connected":
                _LOGGER.warning("WebRTC audio session state is %s", pc.connectionState)
        except Exception:
            self._pc = None
            self._track = None
            await pc.close()
            raise

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
            self._track.stop()
            self._track = None
        if self._pc is not None:
            await self._pc.close()
            self._pc = None
