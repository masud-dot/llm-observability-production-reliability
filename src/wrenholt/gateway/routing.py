"""Where each model is served, and who serves it."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Route:
    # gen_ai.provider.name comes from here, never from the SDK: an
    # OpenAI client pointed at another endpoint is not OpenAI.
    provider: str
    base_url: str
    api_key: str = field(repr=False)

    @property
    def server(self) -> tuple[str, int]:
        url = urlsplit(self.base_url)
        default = 443 if url.scheme == "https" else 80
        return url.hostname or "", url.port or default
