"""Camera platform: the camera's single RTSP stream."""

from __future__ import annotations

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the camera entity."""
    async_add_entities([SonoffCamCamera(entry.runtime_data)])


class SonoffCamCamera(SonoffCamEntity, Camera):
    """The camera's RTSP stream."""

    _attr_name = None
    _attr_brand = "SONOFF"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        SonoffCamEntity.__init__(self, coordinator, "camera")
        # CoordinatorEntity does not chain to Entity.__init__, so the Camera
        # initialiser (access tokens, WebRTC bookkeeping, stream) must run.
        Camera.__init__(self)
        self._attr_model = coordinator.device_info.model if coordinator.device_info else None

    @property
    def use_stream_for_stills(self) -> bool:
        """There is no snapshot endpoint; grab stills from the RTSP stream."""
        return True

    async def stream_source(self) -> str | None:
        """Return the authenticated RTSP URL."""
        return self.coordinator.rtsp_url or None

    @property
    def motion_detection_enabled(self) -> bool:
        """Return whether motion detection is enabled on the device."""
        return self.coordinator.data.motion.enabled

    async def async_enable_motion_detection(self) -> None:
        """Enable motion detection on the device."""
        await self.coordinator.async_write(self.coordinator.client.set_motion_enabled(True))

    async def async_disable_motion_detection(self) -> None:
        """Disable motion detection on the device."""
        await self.coordinator.async_write(self.coordinator.client.set_motion_enabled(False))
