"""Tests for the camera speaker (WebRTC audio) media player."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
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
        await hass.async_block_till_done()

    session.start.assert_awaited_once()
    session.stream_source.assert_awaited_once()
    session.close.assert_awaited_once()
    assert hass.states.get(ENTITY_ID).state == "idle"
