"""Runtime controller API and mocked healing tests."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.models.topology import NodeType
from app.providers.runtime_types import ProviderHealingResult, ProviderReconciliationResult


TOPO_BODY = {
    "name": "Controller Lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _deploy_topology(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "n1",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    dep = client.post(f"/topologies/{tid}/deploy").json()
    return tid, dep["id"]


def test_controller_status(client):
    r = client.get("/controller/status")
    assert r.status_code == 200
    body = r.json()
    assert body["controller_mode"] == "manual"
    assert isinstance(body["managed_deployments_count"], int)
    assert isinstance(body["active_deployments_count"], int)
    assert "docker" in body["supported_providers"]
    assert body["health_summary"]


def test_controller_run_once_processes_active_deployments(client):
    _, did = _deploy_topology(client)
    r = client.post("/controller/run-once")
    assert r.status_code == 200
    payload = r.json()
    assert payload["deployments_checked"] >= 1
    assert payload["drift_detected"] >= 1

    st2 = client.get("/controller/status").json()
    assert st2["last_run_timestamp"] is not None

    ev = client.get(f"/deployments/{did}/events").json()
    msgs = [e["message"] for e in ev]
    assert any("Runtime controller run started" in m for m in msgs)
    assert any("Runtime controller run completed" in m for m in msgs)
    assert any("Drift detected by controller" in m for m in msgs)


def test_controller_run_once_sums_stopped_containers(client, monkeypatch):
    from app.services import runtime_controller as rc

    _deploy_topology(client)
    fake_prov = MagicMock()
    fake_prov.reconcile_runtime.return_value = ProviderReconciliationResult(
        missing_network=False,
        missing_node_ids=(),
        stopped_containers=(("cid001", "node-a"),),
        summary_lines=(),
    )
    monkeypatch.setattr(rc, "runtime_provider_for_topology", lambda _rt: fake_prov)
    j = client.post("/controller/run-once").json()
    assert j["stopped_containers"] >= 1


def test_heal_unknown_deployment_404(client):
    assert client.post(f"/deployments/{uuid.uuid4()}/heal").status_code == 404


def test_heal_fake_provider_records_events(client):
    _, did = _deploy_topology(client)
    r = client.post(f"/deployments/{did}/heal")
    assert r.status_code == 200
    body = r.json()
    assert body["reconciliation_missing_network"] is True
    assert len(body["skipped_missing_resources"]) >= 1

    ev = client.get(f"/deployments/{did}/events").json()
    msgs = [e["message"] for e in ev]
    assert any("Healing started" in m for m in msgs)
    assert any("Healing completed" in m for m in msgs)
    assert any("Healing skipped for missing resource" in m for m in msgs)


def test_heal_restarts_when_provider_reports_stopped(client, monkeypatch):
    """Mock provider: clean reconcile, healing restarts one stopped container."""
    from app.services import runtime_controller as rc

    _, did = _deploy_topology(client)

    fake_prov = MagicMock()
    fake_prov.reconcile_runtime.return_value = ProviderReconciliationResult(
        missing_network=False,
        missing_node_ids=(),
        stopped_containers=(("abcdef00112233445566778899001234567890", "cns-node-x"),),
        summary_lines=("stopped",),
    )
    fake_prov.heal_restart_stopped.return_value = ProviderHealingResult(
        restarted=(
            ("abcdef00112233445566778899001234567890", "cns-node-x"),
        ),
    )

    monkeypatch.setattr(rc, "runtime_provider_for_topology", lambda _rt: fake_prov)

    r = client.post(f"/deployments/{did}/heal")
    assert r.status_code == 200
    j = r.json()
    assert j["reconciliation_stopped_count"] == 1
    assert len(j["restarted_containers"]) == 1
    assert j["restarted_containers"][0]["name"] == "cns-node-x"
    fake_prov.heal_restart_stopped.assert_called_once()

    ev = client.get(f"/deployments/{did}/events").json()
    msgs = [e["message"] for e in ev]
    assert any("Restarting stopped container" in m for m in msgs)
    assert any("Container restarted:" in m for m in msgs)


def test_heal_noop_when_no_drift_mocked(client, monkeypatch):
    from app.services import runtime_controller as rc

    _, did = _deploy_topology(client)

    fake_prov = MagicMock()
    fake_prov.reconcile_runtime.return_value = ProviderReconciliationResult(
        missing_network=False,
        missing_node_ids=(),
        stopped_containers=(),
        summary_lines=("ok",),
    )
    fake_prov.heal_restart_stopped.return_value = ProviderHealingResult()

    monkeypatch.setattr(rc, "runtime_provider_for_topology", lambda _rt: fake_prov)

    r = client.post(f"/deployments/{did}/heal")
    assert r.status_code == 200
    j = r.json()
    assert j["reconciliation_stopped_count"] == 0
    assert j["restarted_containers"] == []
