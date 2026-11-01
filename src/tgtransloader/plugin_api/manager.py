from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from pathlib import Path

from tgtransloader.db import KeyValueStore
from tgtransloader.plugin_api.base import BasePlugin

log = logging.getLogger(__name__)

_PLUGIN_KEY_PREFIX = "plugin:"


class PluginManager:
    """Discover, load, and enable/disable plugins from a directory.

    Plugin files are any ``.py`` file in ``plugins_dir`` whose name does not
    start with ``_``. Each file may define one or more :class:`BasePlugin`
    subclasses. Enable state is persisted via :class:`KeyValueStore`.
    """

    def __init__(self, plugins_dir: Path, db: KeyValueStore):
        self.plugins_dir = plugins_dir
        self.db = db
        self._plugins: dict[str, BasePlugin] = {}

    def load(self) -> None:
        self._plugins.clear()
        if not self.plugins_dir.is_dir():
            log.warning("plugins dir %s does not exist", self.plugins_dir)
            return
        for py_file in sorted(self.plugins_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            self._load_file(py_file)
        log.info("loaded %d plugin(s): %s", len(self._plugins), list(self._plugins))

    def reload(self) -> None:
        for mod_name in list(sys.modules):
            if mod_name.startswith("_tgtl_plugin_"):
                sys.modules.pop(mod_name, None)
        self.load()

    def _load_file(self, py_file: Path) -> None:
        mod_name = f"_tgtl_plugin_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, py_file)
            if spec is None or spec.loader is None:
                log.warning("could not build spec for %s", py_file)
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            log.exception("failed to load plugin %s: %s", py_file, e)
            return
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BasePlugin)
                and obj is not BasePlugin
                and obj.__module__ == mod_name
            ):
                try:
                    plugin = obj()
                except Exception as e:
                    log.exception("failed to instantiate %s: %s", obj, e)
                    continue
                if not plugin.name:
                    log.warning("plugin class %s has empty name, skipping", obj)
                    continue
                self._plugins[plugin.name] = plugin

    def all_plugins(self) -> list[BasePlugin]:
        return list(self._plugins.values())

    def get(self, name: str) -> BasePlugin | None:
        return self._plugins.get(name)

    def _state_key(self, name: str) -> str:
        return f"{_PLUGIN_KEY_PREFIX}{name}:enabled"

    def is_enabled(self, name: str) -> bool:
        return self.db.get(self._state_key(name), "1") == "1"

    def set_enabled(self, name: str, enabled: bool) -> None:
        self.db.put(self._state_key(name), "1" if enabled else "0")

    def toggle(self, name: str) -> bool:
        new_state = not self.is_enabled(name)
        self.set_enabled(name, new_state)
        return new_state

    def find_matching(self, url: str) -> BasePlugin | None:
        for plugin in self._plugins.values():
            if self.is_enabled(plugin.name) and plugin.matches(url):
                return plugin
        return None
