"""Runtime ops delegate to GoRunnerClient when RUNTIME_EXECUTOR=go (same source as /runtime/status)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock
from uuid import UUID

import httpx
import pytest

from app.core import config
from app.db.session import SessionLocal
from app.models.deployment import Deployment, DeploymentStatus
from app.models.topology import Topology, TopologyNode, NodeType
from app.models.user import User
from app.runtime import go_runner_client as grc
from app.schemas.runtime import RuntimeOperationsTrafficRequest
from app.services import runtime_exec_service as exec_svc
from app.services import runtime_operations_service as ops_svc
from app.services.deployment_runtime_resource_service import replace_runtime_resources_from_payload


def _seed_deployment_with_service(
    *, runtime_target: str = "docker"
) -> tuple[UUID, UUID, UUID, UUID]:
    tid = uuid.uuid4()
    did = uuid.uuid4()
    nid = uuid.uuid4()
    uid = uuid.uuid4()
    with SessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=f"ops-{uid.hex[:8]}@example.com",
                password_hash="x",
                display_name="ops",
            )
        )
        db.add(
            Topology(
                id=tid,
                name="ops-delegation",
                description="",
                runtime_target=runtime_target,
                networking_mode="docker_bridge",
            )
        )
        db.add(
            TopologyNode(
                id=nid,
                topology_id=tid,
                name="svc",
                node_type=NodeType.GENERIC,
                image=None,
                ip_address=None,
            )
        )
        db.add(
            Deployment(
                id=did,
                topology_id=tid,
                status=DeploymentStatus.SUCCEEDED,
                runtime_target=runtime_target,
            )
        )
        db.commit()
        replace_runtime_resources_from_payload(
            db,
            did,
            {
                "runtime_provider": runtime_target,
                "namespace_or_network": "cns-net",
                "resources": [
                    {
                        "type": "service",
                        "service_id": nid,
                        "name": "svc",
                        "runtime_name": "cns-node-svc",
                        "status": "running",
                        "internal_url": "http://cns-node-svc:80",
                        "namespace_or_network": "cns-net",
                    },
                ],
            },
        )
        db.commit()
        rows = ops_svc.list_runtime_resources(db, did)
        rid = rows[0].id
    return did, rid, nid, uid


@pytest.fixture
def go_executor(monkeypatch):
    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")


def test_effective_runtime_executor_from_settings_when_env_unset(monkeypatch):
    monkeypatch.delenv("RUNTIME_EXECUTOR", raising=False)
    monkeypatch.setattr(config.settings, "runtime_executor", "go")
    assert grc.effective_runtime_executor() == "go"


def test_should_delegate_ops_under_fake_docker(monkeypatch):
    """Ops use the runner HTTP API; fake Docker only blocks deploy/destroy delegation."""
    monkeypatch.setenv("CNS_USE_FAKE_DOCKER", "1")
    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")
    assert grc.should_delegate_runtime_ops_to_go_runner() is True
    assert grc.use_go_runner_for_docker() is False


def test_runtime_status_and_ops_share_executor_source(client, go_executor, monkeypatch):
    monkeypatch.delenv("RUNTIME_EXECUTOR", raising=False)
    monkeypatch.setattr(config.settings, "runtime_executor", "go")

    def fake_runner_status(self):
        return {
            "status": "ok",
            "runtime_provider": "docker",
            "runtime_executor": "go",
            "docker_reachable": True,
        }

    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.get_runtime_status",
        fake_runner_status,
    )
    status = client.get("/runtime/status").json()
    assert status["runtime_executor"] == "go"
    assert grc.effective_runtime_executor() == "go"
    assert grc.should_delegate_runtime_ops_to_go_runner() is True


def test_health_check_calls_go_runner(go_executor, monkeypatch):
    did, rid, _, uid = _seed_deployment_with_service()
    calls: list[tuple[str, str]] = []

    def fake_health(self, deployment_id, topology_id, workload_node_id, *, project_id=None, body=None):
        calls.append((str(deployment_id), str(workload_node_id)))
        return {
            "status": "passed",
            "target": "http://127.0.0.1:80/",
            "message": "ok",
        }

    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.post_runtime_service_health",
        fake_health,
    )

    with SessionLocal() as db:
        out = ops_svc.run_runtime_health_check(db, did, rid)
    assert out.status == "passed"
    assert len(calls) == 1


def test_health_check_python_fallback_docker_message_no_kubernetes(monkeypatch):
    monkeypatch.setenv("RUNTIME_EXECUTOR", "python")
    monkeypatch.setattr(config.settings, "runtime_executor", "python")
    did, rid, _, _ = _seed_deployment_with_service(runtime_target="docker")

    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        "app.services.runtime_operations_service.httpx.Client",
        _FailingClient,
    )

    with SessionLocal() as db:
        out = ops_svc.run_runtime_health_check(db, did, rid)
    assert out.status == "unsupported"
    assert "Kubernetes" not in (out.message or "")
    assert "Docker" in (out.message or "")


def test_exec_calls_go_runner(go_executor, monkeypatch):
    did, rid, _, uid = _seed_deployment_with_service()
    calls: list[str] = []

    def fake_exec(self, deployment_id, topology_id, workload_node_id, body, *, project_id=None):
        calls.append(str(workload_node_id))
        return {
            "status": "succeeded",
            "stdout": "ok",
            "stderr": "",
            "exit_code": 0,
            "message": "",
        }

    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.post_runtime_service_exec",
        fake_exec,
    )

    with SessionLocal() as db:
        out = exec_svc.run_safe_exec(db, uid, did, rid, "whoami", 10)
    assert out.status == "succeeded"
    assert len(calls) == 1


def test_exec_python_fallback_does_not_call_runner(monkeypatch):
    monkeypatch.setenv("RUNTIME_EXECUTOR", "python")
    monkeypatch.setattr(config.settings, "runtime_executor", "python")
    did, rid, _, uid = _seed_deployment_with_service()
    runner = MagicMock()
    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.post_runtime_service_exec",
        runner,
    )

    with SessionLocal() as db:
        out = exec_svc.run_safe_exec(db, uid, did, rid, "whoami", 10)
    assert out.status == "unsupported"
    assert "RUNTIME_EXECUTOR=go" in (out.message or "")
    runner.assert_not_called()


def test_traffic_test_calls_go_runner(go_executor, monkeypatch):
    did, rid, nid, _ = _seed_deployment_with_service()
    calls: list[dict] = []

    def fake_traffic(self, deployment_id, body):
        calls.append(body)
        return {
            "status": "passed",
            "target": body["target"],
            "protocol": body["protocol"],
            "output": "ok",
        }

    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.post_runtime_traffic_test",
        fake_traffic,
    )

    with SessionLocal() as db:
        out = ops_svc.run_runtime_traffic_test(
            db,
            did,
            RuntimeOperationsTrafficRequest(
                source_runtime_resource_id=rid,
                target=str(nid),
                protocol="ping",
            ),
        )
    assert out.status == "passed"
    assert len(calls) == 1


def test_traffic_test_python_fallback(monkeypatch):
    monkeypatch.setenv("RUNTIME_EXECUTOR", "python")
    monkeypatch.setattr(config.settings, "runtime_executor", "python")
    did, rid, nid, _ = _seed_deployment_with_service()
    runner = MagicMock()
    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.post_runtime_traffic_test",
        runner,
    )

    with SessionLocal() as db:
        out = ops_svc.run_runtime_traffic_test(
            db,
            did,
            RuntimeOperationsTrafficRequest(
                source_runtime_resource_id=rid,
                target=str(nid),
                protocol="ping",
            ),
        )
    assert out.status == "unsupported"
    runner.assert_not_called()
