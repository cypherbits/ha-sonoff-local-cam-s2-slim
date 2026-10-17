"""Speaker entity: play audio / TTS through the camera's speaker.

The audio is streamed to the camera over its local WebRTC endpoint (PCMA/8000),
the same path the eWeLink app uses for two-way audio. This is one-way playback
only (announcements, TTS, sounds) - it does not capture a microphone.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urljoin

import av
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
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.network import get_url

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity
from .webrtc_audio import CameraAudioSession, decode_audio

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the speaker entity."""
    async_add_entities([SonoffCamSpeaker(entry.runtime_data)])


async def _iter_frames(frames: list[av.AudioFrame]) -> AsyncIterator[av.AudioFrame]:
    for frame in frames:
        yield frame


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
        """Play a media source (TTS, URL or local file) on the camera speaker."""
        async with self._lock:
            data = await self._fetch_media(media_id)
            frames = await self.hass.async_add_executor_job(decode_audio, data)
            if not frames:
                raise HomeAssistantError("The media contains no decodable audio")

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
                await session.stream(_iter_frames(frames))
            finally:
                self._session = None
                self._attr_state = MediaPlayerState.IDLE
                self.async_write_ha_state()
                await session.close()

    async def async_media_stop(self) -> None:
        """Stop playback and tear down the WebRTC session."""
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    # ---------------------------------------------------------------- helpers
    async def _fetch_media(self, media_id: str) -> bytes:
        """Resolve a media id to audio bytes."""
        url = media_id
        if media_id.startswith("media-source://"):
            resolved = await media_source.async_resolve_media(self.hass, media_id, self.entity_id)
            url = resolved.url

        if url.startswith("http://") or url.startswith("https://"):
            return await self._download(url)

        if url.startswith("/"):
            if url.startswith(("/api/", "/local/")):
                base = get_url(self.hass, allow_internal=True, allow_ip=True)
                return await self._download(urljoin(base, url))
            if url.startswith("/local/"):
                path = Path(self.hass.config.path("www", url[len("/local/") :]))
                return await self._read_file(path)

        if url.startswith("file://"):
            return await self._read_file(Path(url[len("file://") :]))
        return await self._read_file(Path(url))

    async def _download(self, url: str) -> bytes:
        session = async_get_clientsession(self.hass)
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()

    async def _read_file(self, path: Path) -> bytes:
        def _read() -> bytes:
            if not path.is_file():
                raise HomeAssistantError(f"Media file not found: {path}")
            return path.read_bytes()

        return await self.hass.async_add_executor_job(_read)
