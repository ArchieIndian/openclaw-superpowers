from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def openclaw_dir() -> Path:
    return Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))


def skill_state_file(skill_name: str, filename: str = "state.yaml") -> Path:
    return openclaw_dir() / "skill-state" / skill_name / filename


def now_iso(timespec: str = "seconds") -> str:
    return datetime.now().isoformat(timespec=timespec)


def _default_value(default_factory):
    if callable(default_factory):
        return default_factory()
    return copy.deepcopy(default_factory)


def load_state(path: Path, default_factory) -> dict:
    default_value = _default_value(default_factory)
    if not path.exists():
        return default_value
    try:
        text = path.read_text()
        if HAS_YAML:
            return yaml.safe_load(text) or _default_value(default_factory)
        return json.loads(text)
    except Exception:
        return _default_value(default_factory)


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(path, "w") as handle:
            yaml.dump(state, handle, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        path.write_text(json.dumps(state, indent=2))


def load_structured(path: Path, default_factory=dict):
    if not path.exists():
        return _default_value(default_factory)
    try:
        text = path.read_text()
        if path.suffix == ".json":
            return json.loads(text)
        if HAS_YAML:
            return yaml.safe_load(text) or _default_value(default_factory)
    except Exception:
        pass
    return _default_value(default_factory)
