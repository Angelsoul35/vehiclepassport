"""Compile ``VehicleRegistry.sol`` into the committed ABI + bytecode artifact.

Compilation is delegated to the pinned ``solc-js`` compiler under ``contracts/``
(``node contracts/compile.js``), so no native toolchain is needed and the path is
identical in local development and CI. The committed artifact lets the runtime and
the tests deploy the contract to any JSON-RPC endpoint without a compiler.

Run with ``python -m vehiclepassport.chain.compile`` (or ``make compile``).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"
ARTIFACT_PATH = CONTRACTS_DIR / "artifacts" / "VehicleRegistry.json"


def compile_contract() -> Path:
    npm, node = shutil.which("npm"), shutil.which("node")
    if npm is None or node is None:
        raise RuntimeError("Node.js and npm are required to compile the contract.")
    if not (CONTRACTS_DIR / "node_modules" / "solc").exists():
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=CONTRACTS_DIR, check=True)
    subprocess.run([node, "compile.js"], cwd=CONTRACTS_DIR, check=True)
    return ARTIFACT_PATH


if __name__ == "__main__":
    try:
        print(f"Artifact at {compile_contract()}")
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Compilation failed: {exc}", file=sys.stderr)
        sys.exit(1)
