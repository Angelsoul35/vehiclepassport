from __future__ import annotations

import pytest
from web3 import EthereumTesterProvider, Web3

from vehiclepassport.chain.registry import (
    InMemoryRegistryClient,
    Web3RegistryClient,
    deploy_registry,
)
from vehiclepassport.config import Settings
from vehiclepassport.detector import TamperDetector
from vehiclepassport.service import VehiclePassportService


@pytest.fixture(scope="session")
def detector() -> TamperDetector:
    # Fit once and share; training is deterministic.
    return TamperDetector(max_km_per_day=1500.0, risk_threshold=0.5).fit()


@pytest.fixture
def w3() -> Web3:
    return Web3(EthereumTesterProvider())


@pytest.fixture
def chain_registry(w3) -> Web3RegistryClient:
    operator = w3.eth.accounts[0]
    return Web3RegistryClient(w3, deploy_registry(w3, operator), operator)


@pytest.fixture
def settings() -> Settings:
    return Settings(chain_enabled=False, risk_threshold=0.5, max_km_per_day=1500.0)


@pytest.fixture
def service(settings, detector) -> VehiclePassportService:
    return VehiclePassportService(
        settings=settings, registry=InMemoryRegistryClient(), detector=detector
    )
