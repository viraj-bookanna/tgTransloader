from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Pattern

if TYPE_CHECKING:
    from tgtransloader.config import Config


@dataclass
class PluginContext:
    """Everything a plugin needs from the host application."""

    config: "Config"
    download_dir: Path


class BasePlugin(ABC):
    """Base class for site-specific download plugins.

    Subclass this, set ``name`` and ``url_patterns``, implement :meth:`download`,
    then drop the file into the configured plugins directory.
    """

    name: str = ""
    description: str = ""
    url_patterns: Iterable[str | Pattern[str]] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._compiled = [
            p if hasattr(p, "search") else re.compile(p)
            for p in cls.url_patterns
        ]

    def matches(self, url: str) -> bool:
        return any(p.search(url) for p in self._compiled)

    @abstractmethod
    async def download(self, url: str, event, ctx: PluginContext) -> str:
        """Download the resource at ``url``.

        Should edit ``event`` with progress updates and return the primary
        downloaded file path (inside ``ctx.download_dir``).
        """
        raise NotImplementedError
