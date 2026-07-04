"""Transit provider adapters."""

from blix.providers.base import TransitProvider
from blix.providers.delhi_otd import DelhiOTDProvider

_REGISTRY: dict[str, type[TransitProvider]] = {
    DelhiOTDProvider.provider_id: DelhiOTDProvider,
}


def get_provider(provider_id: str = "delhi-otd") -> TransitProvider:
    try:
        return _REGISTRY[provider_id]()
    except KeyError as exc:
        raise ValueError(f"Unknown provider: {provider_id!r}") from exc


__all__ = ["TransitProvider", "DelhiOTDProvider", "get_provider"]
