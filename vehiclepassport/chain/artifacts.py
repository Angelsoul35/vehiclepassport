"""Load the committed contract artifact (ABI + bytecode)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "artifacts" / "VehicleRegistry.json"
)


@lru_cache(maxsize=1)
def load_artifact() -> dict:
    if not ARTIFACT_PATH.exists():
        raise FileNotFoundError(
            f"Contract artifact not found at {ARTIFACT_PATH}. Run `make compile` first."
        )
    return json.loads(ARTIFACT_PATH.read_text())


def contract_abi() -> list:
    return load_artifact()["abi"]


def contract_bytecode() -> str:
    return load_artifact()["bytecode"]
