"""Speaker entity: play audio / TTS / radio through the camera's speaker.

The audio is streamed to the camera over its local WebRTC endpoint (PCMA/8000),
the same path the eWeLink app uses for two-way audio. This is one-way playback
only (announcements, TTS, sounds, internet radio) - it does not capture a mic.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.network import get_url

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity
from .webrtc_audio import CameraAudioSession

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the speaker entity."""
    async_add_entities([SonoffCamSpeaker(entry.runtime_data)])


class SonoffCamSpeaker(SonoffCamEntity, MediaPlayerEntity):
    """Play audio through the camera's built-in speaker."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_translation_key = "speaker"
    _attr_supported_features = (
        MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
    )

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        super().__init__(coordinator, "speaker")
        self._session: CameraAudioSession | None = None
        self._lock = asyncio.Lock()
        self._attr_state = MediaPlayerState.IDLE

    # ------------------------------------------------------------------ state
    @property
    def state(self) -> MediaPlayerState:
        """Return the player state."""
        return self._attr_state

    @property
    def volume_level(self) -> float | None:
        """Return the camera speaker volume as 0.0-1.0."""
        volume = self.coordinator.data.speaker.get("speakerVolume")
        return round(float(volume) / 100, 2) if volume is not None else None

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the camera speaker volume."""
        level = max(0, min(100, round(volume * 100)))
        await self.coordinator.async_write(
            self.coordinator.client.set_speaker_config(
                {**self.coordinator.data.speaker, "speakerVolume": level}
            )
        )

    # ----------------------------------------------------------------- browse
    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
        **kwargs: object,
    ) -> BrowseMedia:
        """Expose Home Assistant's media sources through the speaker.

        The media browser only lists players that advertise ``BROWSE_MEDIA``, so
        this delegate is what makes the speaker selectable as a playback target
        (e.g. to play a radio station or TTS on it).
        """
        return await media_source.async_browse_media(self.hass, media_content_id)

    # --------------------------------------------------------------- playback
    async def async_play_media(self, media_type: str, media_id: str, **kwargs: object) -> None:
        """Play a media source (radio, TTS, URL or file) on the camera speaker."""
        source = await self._resolve_source(media_id)

        async with self._lock:
            session = CameraAudioSession(self.coordinator.client.raw_call)
            try:
                await session.start()
            except Exception as err:
                raise HomeAssistantError(
                    f"Could not open the camera WebRTC audio session: {err}"
                ) from err

            self._session = session
            self._attr_state = MediaPlayerState.PLAYING
            self.async_write_ha_state()
            try:
                await session.stream_source(source)
            except Exception as err:
                raise HomeAssistantError(f"Playback failed: {err}") from err
            finally:
                self._session = None
                self._attr_state = MediaPlayerState.IDLE
                self.async_write_ha_state()
                await session.close()

    async def async_media_stop(self) -> None:
        """Stop playback and tear down the WebRTC session."""
        session, self._session = self._session, None
        if session is not None:
            await session.close()
        self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    # ---------------------------------------------------------------- helpers
    async def _resolve_source(self, media_id: str) -> str:
        """Resolve a media id to a URL or local path usable by ffmpeg/PyAV."""
        url = media_id
        if media_id.startswith("media-source://"):
            resolved = await media_source.async_resolve_media(self.hass, media_id, self.entity_id)
            url = resolved.url

        if url.startswith(("http://", "https://", "rtsp://", "rtmp://")):
            return url
        if url.startswith("file://"):
            return url[len("file://") :]
        if url.startswith("/local/"):
            return self.hass.config.path("www", url[len("/local/") :])
        if url.startswith("/"):
            try:
                base = get_url(self.hass, allow_internal=True, allow_ip=True)
            except HomeAssistantError:
                base = None
            if base is not None:
                return urljoin(base, url)
        return url
