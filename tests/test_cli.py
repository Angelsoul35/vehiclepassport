from __future__ import annotations

import pytest

from vehiclepassport import cli

pytestmark = pytest.mark.chain


def test_demo_runs_end_to_end(capsys):
    cli.demo()
    out = capsys.readouterr().out
    assert "Deploying VehicleRegistry" in out
    assert "recorded" in out
    assert "odometer rollback" in out
    assert "suspicious: True" in out


def test_main_dispatches_demo(monkeypatch):
    called = {"demo": False}
    monkeypatch.setattr(cli, "demo", lambda: called.__setitem__("demo", True))
    monkeypatch.setattr("sys.argv", ["vehiclepassport", "demo"])
    cli.main()
    assert called["demo"] is True
