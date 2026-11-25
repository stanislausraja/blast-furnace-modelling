"""Blast furnace numerical model (pure Python, runs in CPython and in the browser via Pyodide)."""

import json

from . import registry

__version__ = "0.1.0"


def schema_json():
    return json.dumps(registry.schema())


def run_json(inputs_json="{}"):
    return json.dumps(registry.run(json.loads(inputs_json)), allow_nan=False, default=str)
