"""Step 51A: integration outputs API."""

from __future__ import annotations

import uuid
from uuid import UUID

from app.db.session import SessionLocal
from app.models.topology import NodeType
from app.services.deployment_runtime_resource_service import replace_runtime_resources_from_payload
from app.services.integration_outputs_service import OUTPUT_LANGUAGE_KEYS

TOPO = {
    "name": "integration-outputs-lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _seed_service(
    client,
    *,
    internal_url: str = "http://cns-node-web:80",
    external_url: str | None = None,
    name: str = "api",
):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    nid = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": name,
            "node_type": NodeType.HOST.value,
            "image": "nginx:alpine",
            "config": None,
        },
    ).json()["id"]
    did = client.post(f"/topologies/{tid}/deploy").json()["id"]
    with SessionLocal() as db:
        replace_runtime_resources_from_payload(
            db,
            UUID(did),
            {
                "runtime_provider": "docker",
                "resources": [
                    {
                        "type": "service",
                        "service_id": nid,
                        "name": name,
                        "runtime_name": f"cns-node-{name}",
                        "internal_url": internal_url,
                        "external_url": external_url,
                        "ports": [{"port": 80, "target_port": 80, "protocol": "TCP"}],
                    },
                ],
            },
        )
        db.commit()
    return tid, did, nid


def _reg(client_strict, prefix: str) -> tuple[str, dict[str, str]]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "IO"},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_integration_outputs_returns_services_and_all_language_keys(client):
    _, did, _ = _seed_service(client)
    r = client.get(f"/deployments/{did}/integration-outputs")
    assert r.status_code == 200
    body = r.json()
    assert body["deployment_id"] == did
    assert body["runtime_provider"]
    assert len(body["services"]) == 1
    svc = body["services"][0]
    assert svc["name"] == "api"
    assert svc["internal_url"] == "http://cns-node-web:80"
    assert svc["endpoint_scope"] == "internal_only"
    assert "Internal runtime URL" in (svc["url_note"] or "")
    assert svc["recommended_env_var"] == "API_SERVICE_URL"
    outputs = body["outputs"]
    for key in OUTPUT_LANGUAGE_KEYS:
        assert key in outputs
        assert isinstance(outputs[key], str)
    assert "API_SERVICE_URL=" in outputs["env"]
    assert "curl -sS" in outputs["curl"]


def test_external_url_preferred_for_outside_snippets(client):
    _, did, _ = _seed_service(
        client,
        internal_url="http://cns-node-api:80",
        external_url="http://127.0.0.1:18080/",
        name="api",
    )
    body = client.get(f"/deployments/{did}/integration-outputs").json()
    svc = body["services"][0]
    assert svc["external_url"] == "http://127.0.0.1:18080/"
    assert svc["preferred_url"] == "http://127.0.0.1:18080/"
    assert svc["endpoint_scope"] == "external"
    assert svc["url_note"] is None
    assert "127.0.0.1:18080" in body["outputs"]["env"]


def test_env_var_names_are_safe(client):
    _, did, _ = _seed_service(client, name="my-api gateway!")
    svc = client.get(f"/deployments/{did}/integration-outputs").json()["services"][0]
    assert svc["recommended_env_var"] == "MY_API_GATEWAY_SERVICE_URL"


def test_unauthorized_user_blocked(client_strict):
    ha, _ = _reg(client_strict, "ioo")
    _, hb = _reg(client_strict, "iox")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    tid = client_strict.post(
        "/topologies",
        headers=ha,
        json={**TOPO, "project_id": pid},
    ).json()["id"]
    did = client_strict.post(f"/topologies/{tid}/deploy", headers=ha).json()["id"]
    r = client_strict.get(f"/deployments/{did}/integration-outputs", headers=hb)
    assert r.status_code == 404


def test_viewer_can_read_integration_outputs(client_strict):
    _, owner_h = _reg(client_strict, "iovown")
    viewer_email, viewer_h = _reg(client_strict, "ioview")
    pid = client_strict.get("/projects", headers=owner_h).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=owner_h,
            json={"email": viewer_email, "role": "viewer"},
        ).status_code
        == 201
    )
    tid = client_strict.post(
        "/topologies",
        headers=owner_h,
        json={**TOPO, "project_id": pid},
    ).json()["id"]
    did = client_strict.post(f"/topologies/{tid}/deploy", headers=owner_h).json()["id"]
    r = client_strict.get(f"/deployments/{did}/integration-outputs", headers=viewer_h)
    assert r.status_code == 200
