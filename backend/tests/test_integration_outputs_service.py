"""Unit tests for integration output generation (no DB)."""

from __future__ import annotations

from uuid import uuid4

from app.schemas.integration_outputs import IntegrationServiceOutput
from app.services.integration_outputs_service import (
    INTERNAL_ONLY_NOTE,
    OUTPUT_LANGUAGE_KEYS,
    _catalog_services,
    _safe_env_base,
    build_integration_outputs_bundle,
)


def test_safe_env_base_sanitizes_names():
    assert _safe_env_base("my-api gateway!") == "MY_API_GATEWAY"
    assert _safe_env_base("") == "SERVICE"


def test_catalog_prefers_external_url():
    resources = [
        {
            "id": str(uuid4()),
            "type": "service",
            "name": "api",
            "runtime_name": "cns-api",
            "internal_url": "http://cns-api:80",
            "external_url": "http://127.0.0.1:8080/",
            "ports": [{"port": 80, "target_port": 80}],
        }
    ]
    services = _catalog_services(resources, [])
    assert len(services) == 1
    svc = services[0]
    assert svc.endpoint_scope == "external"
    assert svc.preferred_url == "http://127.0.0.1:8080/"
    assert svc.url_note is None


def test_catalog_marks_internal_only():
    resources = [
        {
            "id": str(uuid4()),
            "type": "service",
            "name": "web",
            "internal_url": "http://cns-web:80",
            "ports": [{"port": 80, "target_port": 80}],
        }
    ]
    svc = _catalog_services(resources, [])[0]
    assert svc.endpoint_scope == "internal_only"
    assert svc.url_note == INTERNAL_ONLY_NOTE
    assert svc.recommended_env_var == "WEB_SERVICE_URL"


def test_all_output_language_keys_present():
    dep = uuid4()
    topo = uuid4()
    services = [
        IntegrationServiceOutput(
            name="api",
            preferred_url="http://127.0.0.1:8080",
            endpoint_scope="external",
            recommended_env_var="API_SERVICE_URL",
            env_vars={"API_SERVICE_URL": "http://127.0.0.1:8080"},
        )
    ]
    env = {"CNS_DEPLOYMENT_ID": str(dep), "API_SERVICE_URL": "http://127.0.0.1:8080"}
    bundle = build_integration_outputs_bundle(
        env=env, services=services, dep_id=dep, topo_id=topo
    )
    data = bundle.model_dump()
    for key in OUTPUT_LANGUAGE_KEYS:
        assert key in data
        assert isinstance(data[key], str)
        assert len(data[key]) > 0
