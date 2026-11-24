"""Tests for the camera speaker (WebRTC audio) media player."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.media_source.models import PlayMedia
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonoff_cam_local.const import (
    CONF_ENABLE_ONVIF,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    DOMAIN,
)
from custom_components.sonoff_cam_local.media_player import SonoffCamSpeaker

from .fakes import PASSWORD, FakeSonoffCamera

ENTITY_ID = "media_player.cam_s2_speaker"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    # Home Assistant normally adds these directories during startup. The test
    # harness skips that step, so mirror it here for the path checks.
    hass.config.allowlist_external_dirs.update(
        {hass.config.path("www"), hass.config.path("media")}
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: PASSWORD},
        options={CONF_ENABLE_ONVIF: False},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sonoff_cam_local.coordinator.SonoffCamera", FakeSonoffCamera):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_speaker_entity_exists(hass: HomeAssistant) -> None:
    """The setup creates the speaker media player."""
    await _setup(hass)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "idle"


async def test_speaker_supports_play_and_browse(hass: HomeAssistant) -> None:
    """The speaker advertises PLAY_MEDIA and BROWSE_MEDIA.

    The HA media browser only lists players that support ``BROWSE_MEDIA``, so
    this must stay set or the camera disappears from the playback targets.
    """
    from homeassistant.components.media_player import MediaPlayerEntityFeature

    await _setup(hass)
    features = hass.states.get(ENTITY_ID).attributes["supported_features"]
    assert features & MediaPlayerEntityFeature.PLAY_MEDIA
    assert features & MediaPlayerEntityFeature.BROWSE_MEDIA


async def test_play_media_opens_webrtc_session(hass: HomeAssistant) -> None:
    """play_media streams decoded audio through a WebRTC session."""
    await _setup(hass)

    session = MagicMock()
    session.start = AsyncMock()
    session.stream_source = AsyncMock()
    session.close = AsyncMock()

    with (
        patch.object(
            SonoffCamSpeaker,
            "_resolve_source",
            AsyncMock(return_value="http://example.com/radio.mp3"),
        ),
        patch(
            "custom_components.sonoff_cam_local.media_player.CameraAudioSession",
            return_value=session,
        ),
    ):
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": ENTITY_ID,
                "media_content_id": "media-source://tts/tts.test",
                "media_content_type": "music",
            },
            blocking=True,
        )
        entity = hass.data["media_player"].get_entity(ENTITY_ID)
        assert entity is not None
        if entity._play_task is not None:
            await entity._play_task
        await hass.async_block_till_done()

    session.start.assert_awaited_once()
    session.stream_source.assert_awaited_once()
    session.close.assert_awaited_once()
    assert hass.states.get(ENTITY_ID).state == "idle"


def _touch(path: Path) -> None:
    """Create an empty file and its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


async def test_resolve_source_accepts_urls_and_allowed_paths(hass: HomeAssistant) -> None:
    """Remote URLs and media files inside allowed directories are accepted."""
    await _setup(hass)
    entity = hass.data["media_player"].get_entity(ENTITY_ID)
    assert entity is not None

    for url in (
        "http://example.com/radio.mp3",
        "https://example.com/radio.mp3",
        "rtsp://example.com/stream",
        "rtmp://example.com/stream",
    ):
        assert await entity._resolve_source(url) == url

    www_file = Path(hass.config.path("www", "chime.mp3"))
    await hass.async_add_executor_job(_touch, www_file)
    assert await entity._resolve_source("/local/chime.mp3") == str(www_file)

    media_file = Path(hass.config.path("media", "chime.mp3"))
    await hass.async_add_executor_job(_touch, media_file)
    assert await entity._resolve_source(str(media_file)) == str(media_file)
    assert await entity._resolve_source(media_file.as_uri()) == str(media_file)


async def test_resolve_source_accepts_resolved_media_source(hass: HomeAssistant) -> None:
    """A media source URL is resolved before it is handed to the decoder."""
    await _setup(hass)
    entity = hass.data["media_player"].get_entity(ENTITY_ID)
    assert entity is not None

    media_file = Path(hass.config.path("media", "resolved.mp3"))
    await hass.async_add_executor_job(_touch, media_file)
    resolved = PlayMedia(
        url="/media/local/resolved.mp3", mime_type="audio/mpeg", path=media_file
    )
    with patch(
        "custom_components.sonoff_cam_local.media_player.media_source.async_resolve_media",
        AsyncMock(return_value=resolved),
    ):
        assert (
            await entity._resolve_source(
                "media-source://media_source/local/resolved.mp3"
            )
            == str(media_file)
        )


async def test_resolve_source_rejects_disallowed_paths(hass: HomeAssistant) -> None:
    """Arbitrary filesystem paths and unsupported ids are rejected."""
    await _setup(hass)
    entity = hass.data["media_player"].get_entity(ENTITY_ID)
    assert entity is not None

    for media_id in (
        "/etc/passwd",
        "file:///etc/passwd",
        "relative.mp3",
        "/local/../../etc/passwd",
    ):
        with pytest.raises(HomeAssistantError):
            await entity._resolve_source(media_id)


async def test_play_media_rejects_disallowed_path(hass: HomeAssistant) -> None:
    """A disallowed path is rejected before any WebRTC session is opened."""
    await _setup(hass)

    with (
        patch(
            "custom_components.sonoff_cam_local.media_player.CameraAudioSession"
        ) as session_cls,
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": ENTITY_ID,
                "media_content_id": "/etc/passwd",
                "media_content_type": "music",
            },
            blocking=True,
        )

    session_cls.assert_not_called()
