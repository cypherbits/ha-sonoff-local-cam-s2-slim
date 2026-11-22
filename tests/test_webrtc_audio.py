"""Tests for the subprocess audio decoder."""

from __future__ import annotations

import wave
from fractions import Fraction
from pathlib import Path

from custom_components.sonoff_cam_local.webrtc_audio import (
    _TARGET_RATE,
    AudioSourceStreamer,
)


def _write_wav(path: Path, seconds: float) -> None:
    frames = int(8000 * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * frames)


def test_streamer_decodes_to_48k_frames(tmp_path: Path) -> None:
    """Decoded audio is returned as 20 ms s16 48 kHz frames."""
    source = tmp_path / "tone.wav"
    _write_wav(source, 0.1)

    streamer = AudioSourceStreamer(str(source))
    frames = list(streamer.frames())

    assert len(frames) >= 5
    assert frames[0].sample_rate == _TARGET_RATE
    assert frames[0].samples == 960
    assert frames[0].time_base == Fraction(1, _TARGET_RATE)
    assert frames[0].format.name == "s16"
    assert frames[0].layout.name == "mono"


def test_streamer_close_stops_decoder(tmp_path: Path) -> None:
    """Closing the streamer terminates the child process promptly."""
    source = tmp_path / "long.wav"
    _write_wav(source, 10)

    streamer = AudioSourceStreamer(str(source))
    frames = streamer.frames()
    assert next(frames) is not None
    streamer.close()
    # The worker is still inside the generator; closing must end it on the
    # next read instead of decoding the whole file.
    frames.close()
