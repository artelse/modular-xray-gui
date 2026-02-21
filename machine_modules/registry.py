"""
Discover machine_modules packages and their metadata.
Enables adding modules without editing gui.py: each module declares MODULE_INFO
and optionally get_setting_keys(); the GUI uses this to build Settings checkboxes
and load/save module-specific settings.
"""

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any

# Base package name for discovery (this file is machine_modules/registry.py)
MACHINE_MODULES_PACKAGE = "machine_modules"


def _discover_package_names() -> list[str]:
    """Return list of subpackage names under machine_modules (e.g. ['faxitron', 'esp_hv_supply'])."""
    try:
        mod = sys.modules.get(MACHINE_MODULES_PACKAGE)
        if mod is None:
            mod = importlib.import_module(MACHINE_MODULES_PACKAGE)
        pkgpath = getattr(mod, "__path__", None)
        if pkgpath is None:
            return []
        names = []
        for _importer, name, _ispkg in pkgutil.iter_modules(pkgpath):
            # Skip registry and private / internal names
            if name.startswith("_") or name == "registry":
                continue
            names.append(name)
        return sorted(names)
    except Exception:
        return []


def get_module_info(name: str) -> dict[str, Any]:
    """
    Import machine_modules.<name> and return its MODULE_INFO (or defaults).
    Returns dict with: display_name, description, type ("camera"|"machine"|"alteration"|"manual_alteration"|"workflow_automation"),
    default_enabled, camera_priority (only for type "camera"), pipeline_slot (only for type "alteration"), setting_keys (list).
    """
    defaults = {
        "display_name": name.replace("_", " ").title(),
        "description": "Applies on next startup.",
        "type": "machine",
        "default_enabled": False,
        "camera_priority": 0,
        "pipeline_slot": 0,  # For type "alteration": order in image pipeline (e.g. 100=dark, 200=flat)
        "setting_keys": [],
    }
    try:
        mod = importlib.import_module(f"{MACHINE_MODULES_PACKAGE}.{name}")
        info = getattr(mod, "MODULE_INFO", None)
        if isinstance(info, dict):
            defaults.update(info)
        # get_setting_keys() can add keys we persist for this module
        get_sk = getattr(mod, "get_setting_keys", None)
        if callable(get_sk):
            try:
                keys = get_sk()
                if isinstance(keys, (list, tuple)):
                    defaults["setting_keys"] = list(keys)
            except Exception:
                pass
    except Exception:
        pass
    return defaults


def discover_modules() -> list[dict[str, Any]]:
    """
    Return list of module info dicts for all discovered packages under machine_modules.
    Each dict has: name, display_name, description, type, default_enabled,
    camera_priority (if camera), setting_keys.
    """
    result = []
    for name in _discover_package_names():
        info = get_module_info(name)
        info["name"] = name
        result.append(info)
    return result


def all_extra_settings_keys(modules: list[dict[str, Any]]) -> set[str]:
    """Return set of all setting keys to persist: load_<name>_module plus each module's setting_keys."""
    keys = set()
    for m in modules:
        keys.add(f"load_{m['name']}_module")
        keys.update(m.get("setting_keys") or [])
    return keys


def collect_module_defaults(modules: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Collect default settings from all modules.
    Returns dict of {key: default_value} from each module's get_default_settings().
    Also includes load_<name>_module defaults from MODULE_INFO.default_enabled.
    """
    defaults = {}
    for m in modules:
        module_name = m["name"]
        # Module enable flag default from MODULE_INFO
        defaults[f"load_{module_name}_module"] = m.get("default_enabled", False)
        # Module-specific settings defaults
        try:
            mod = importlib.import_module(f"{MACHINE_MODULES_PACKAGE}.{module_name}")
            get_defaults = getattr(mod, "get_default_settings", None)
            if callable(get_defaults):
                try:
                    module_defaults = get_defaults()
                    if isinstance(module_defaults, dict):
                        defaults.update(module_defaults)
                except Exception:
                    pass
        except Exception:
            pass
    return defaults
