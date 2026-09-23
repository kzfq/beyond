"""Tiny persistence shim for Beyond — JSON file next to the backend.

Provides the same surface the RPC cog expects:
    persistence.get(key, default)
    persistence.set_key(key, value)
    persistence.instance_dir()
"""
import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_DIR, "beyond_state.json")
_data = None


def _load():
    global _data
    if _data is None:
        try:
            with open(_PATH, "r", encoding="utf-8") as f:
                _data = json.load(f)
        except Exception:
            _data = {}
    return _data


def get(key, default=None):
    return _load().get(key, default)


def set_key(key, value):
    d = _load()
    d[key] = value
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


def instance_dir():
    return _DIR
