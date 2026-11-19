"""Public feature flags published by the authenticated administration service."""

import json
from pathlib import Path
from django.conf import settings
from .aggregate_release import _atomic_json

DEFAULTS = {"trend": True, "map": True}


def availability():
    path = Path(settings.PUBLIC_RELEASE_ROOT) / "visualizations.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DEFAULTS.copy()
    except (OSError, ValueError):
        return dict.fromkeys(DEFAULTS, False)
    if not isinstance(data, dict):
        return dict.fromkeys(DEFAULTS, False)
    return {name: data.get(name) is True for name in DEFAULTS}


def save_availability(values):
    _atomic_json(
        Path(settings.PUBLIC_RELEASE_ROOT) / "visualizations.json",
        {name: values.get(name) is True for name in DEFAULTS},
    )
