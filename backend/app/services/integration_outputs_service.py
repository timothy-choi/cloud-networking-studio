"""Step 51A: generate integration outputs for apps, CI/CD, Docker Compose, and Kubernetes."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.deployment import Deployment
from app.models.topology import Topology
from app.schemas.integration_outputs import (
    DeploymentIntegrationOutputsResponse,
    IntegrationOutputFileItem,
    IntegrationOutputsBundle,
    IntegrationServiceOutput,
)
from app.services.deployment_runtime_resource_service import (
    list_runtime_resources,
    resource_row_to_public_dict,
)
from app.services.deployment_service_exposure_service import (
    exposure_to_api_dict,
    list_exposure_rows,
)
from app.services.runtime_state_service import build_deployment_runtime

INTERNAL_ONLY_NOTE = (
    "Internal runtime URL — usable from inside the topology/runtime network only."
)

OUTPUT_LANGUAGE_KEYS = (
    "env",
    "curl",
    "bash",
    "python",
    "javascript",
    "typescript",
    "java",
    "go",
    "ruby",
    "php",
    "csharp",
    "github_actions",
    "docker_compose_env",
    "kubernetes_configmap",
)


@dataclass(frozen=True)
class IntegrationOutputFileSpec:
    name: str
    type: str
    output_key: str
    media_type: str


INTEGRATION_OUTPUT_FILE_SPECS: tuple[IntegrationOutputFileSpec, ...] = (
    IntegrationOutputFileSpec("cns.env", "env", "env", "text/plain; charset=utf-8"),
    IntegrationOutputFileSpec("cns-integration.sh", "bash", "bash", "application/x-sh; charset=utf-8"),
    IntegrationOutputFileSpec("cns_integration.py", "python", "python", "text/x-python; charset=utf-8"),
    IntegrationOutputFileSpec("cns-integration.js", "javascript", "javascript", "text/javascript; charset=utf-8"),
    IntegrationOutputFileSpec("cns-integration.ts", "typescript", "typescript", "text/typescript; charset=utf-8"),
    IntegrationOutputFileSpec("CnsIntegration.java", "java", "java", "text/x-java-source; charset=utf-8"),
    IntegrationOutputFileSpec("cns_integration.go", "go", "go", "text/x-go; charset=utf-8"),
    IntegrationOutputFileSpec("cns_integration.rb", "ruby", "ruby", "application/x-ruby; charset=utf-8"),
    IntegrationOutputFileSpec("cns_integration.php", "php", "php", "application/x-httpd-php; charset=utf-8"),
    IntegrationOutputFileSpec("CnsIntegration.cs", "csharp", "csharp", "text/x-csharp; charset=utf-8"),
    IntegrationOutputFileSpec(
        "github-actions-cns.yml", "github_actions", "github_actions", "application/yaml; charset=utf-8"
    ),
    IntegrationOutputFileSpec(
        "docker-compose.env", "docker_compose_env", "docker_compose_env", "text/plain; charset=utf-8"
    ),
    IntegrationOutputFileSpec(
        "kubernetes-configmap.yaml",
        "kubernetes_configmap",
        "kubernetes_configmap",
        "application/yaml; charset=utf-8",
    ),
)

ALLOWED_INTEGRATION_FILENAMES: frozenset[str] = frozenset(s.name for s in INTEGRATION_OUTPUT_FILE_SPECS)
INTEGRATION_FILES_BY_NAME: dict[str, IntegrationOutputFileSpec] = {
    s.name: s for s in INTEGRATION_OUTPUT_FILE_SPECS
}


def _safe_env_base(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (name or "service").strip().upper())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "SERVICE"


def _primary_port(ports: Any) -> int | None:
    if not isinstance(ports, list) or not ports:
        return None
    first = ports[0]
    if not isinstance(first, dict):
        return None
    for key in ("port", "target_port"):
        val = first.get(key)
        if isinstance(val, int) and val > 0:
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return None


def _protocol_from_url(url: str | None, port: int | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme:
        if parsed.scheme in ("http", "https"):
            return parsed.scheme.upper()
        return parsed.scheme.lower()
    if port == 443:
        return "HTTPS"
    if port:
        return "TCP"
    return None


def _exposure_urls_by_resource(exposures: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in exposures:
        if e.get("status") != "active":
            continue
        url = e.get("external_url")
        rid = e.get("runtime_resource_id")
        if url and rid:
            out[str(rid)] = str(url)
    return out


def _env_vars_for_service(name: str, preferred: str | None, internal: str | None, port: int | None) -> tuple[str, dict[str, str]]:
    base = _safe_env_base(name)
    lower = name.lower()
    env: dict[str, str] = {}
    primary = preferred or internal
    if not primary:
        return f"{base}_URL", env

    parsed = urlparse(primary) if "://" in primary else None
    scheme = (parsed.scheme if parsed else "").lower()

    if scheme == "redis" or "redis" in lower:
        key = "REDIS_URL" if base in ("REDIS", "CACHE") else f"{base}_URL"
        env[key] = primary
        return key, env

    if scheme in ("postgres", "postgresql") or "postgres" in lower:
        host = parsed.hostname if parsed else primary.split(":")[0]
        p = parsed.port if parsed and parsed.port else (port or 5432)
        env["POSTGRES_HOST"] = host or primary
        env["POSTGRES_PORT"] = str(p)
        if parsed and parsed.path and parsed.path != "/":
            env["POSTGRES_DB"] = parsed.path.lstrip("/")
        return "POSTGRES_HOST", env

    if scheme in ("http", "https") or primary.startswith("http"):
        key = f"{base}_URL" if base.endswith("SERVICE") else f"{base}_SERVICE_URL"
        if key == "SERVICE_SERVICE_URL":
            key = "SERVICE_URL"
        env[key] = primary
        return key, env

    key = f"{base}_URL"
    env[key] = primary
    if port and f"{base}_PORT" not in env:
        env[f"{base}_PORT"] = str(port)
    return key, env


def _catalog_services(
    resources: list[dict[str, Any]], exposures: list[dict[str, Any]]
) -> list[IntegrationServiceOutput]:
    exposure_map = _exposure_urls_by_resource(exposures)
    services: list[IntegrationServiceOutput] = []
    for r in resources:
        if r.get("type") != "service":
            continue
        name = str(r.get("name") or r.get("runtime_name") or "service")
        internal = r.get("internal_url")
        external = r.get("external_url") or exposure_map.get(str(r.get("id") or ""))
        port = _primary_port(r.get("ports"))
        if not port and internal:
            try:
                port = urlparse(str(internal)).port
            except Exception:
                port = None

        if external:
            preferred = str(external)
            scope = "external"
            note = None
        elif internal:
            preferred = str(internal)
            scope = "internal_only"
            note = INTERNAL_ONLY_NOTE
        else:
            preferred = None
            scope = "internal_only"
            note = None

        env_key, env_vars = _env_vars_for_service(name, preferred, internal, port)
        services.append(
            IntegrationServiceOutput(
                name=name,
                runtime_name=r.get("runtime_name"),
                internal_url=str(internal) if internal else None,
                external_url=str(external) if external else None,
                preferred_url=preferred,
                endpoint_scope=scope,
                url_note=note,
                protocol=_protocol_from_url(preferred or internal, port),
                port=port,
                recommended_env_var=env_key,
                env_vars=env_vars,
            )
        )
    return services


def _merged_env(services: list[IntegrationServiceOutput], dep_id: UUID, topo_id: UUID) -> dict[str, str]:
    env: dict[str, str] = {
        "CNS_DEPLOYMENT_ID": str(dep_id),
        "CNS_TOPOLOGY_ID": str(topo_id),
    }
    for svc in services:
        env.update(svc.env_vars)
    return env


def _env_snippet(env: dict[str, str], services: list[IntegrationServiceOutput]) -> str:
    lines: list[str] = ["# CNS integration outputs — copy into your app or .env file"]
    for svc in services:
        if svc.endpoint_scope == "internal_only" and svc.preferred_url:
            lines.append(f"# {svc.name}: {INTERNAL_ONLY_NOTE}")
    for k, v in env.items():
        lines.append(f"{k}={v}")
    return "\n".join(lines) + "\n"


def _pick_example_url(services: list[IntegrationServiceOutput]) -> str | None:
    for svc in services:
        if svc.endpoint_scope == "external" and svc.preferred_url:
            return svc.preferred_url
    for svc in services:
        if svc.preferred_url:
            return svc.preferred_url
    return None


def _curl_snippet(services: list[IntegrationServiceOutput]) -> str:
    if not services:
        return "# No service URLs available yet — deploy and refresh runtime access.\n"
    lines = ["# HTTP/TCP checks against CNS deployment services"]
    for svc in services:
        url = svc.preferred_url
        if not url:
            continue
        prefix = ""
        if svc.endpoint_scope == "internal_only":
            prefix = f"# INTERNAL ONLY — {svc.name}\n"
        lines.append(f"{prefix}curl -sS {url!r}")
    return "\n".join(lines) + "\n"


def _bash_snippet(env: dict[str, str], services: list[IntegrationServiceOutput]) -> str:
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    for svc in services:
        if svc.endpoint_scope == "internal_only" and svc.preferred_url:
            lines.append(f"# {svc.name}: {INTERNAL_ONLY_NOTE}")
    for k, v in env.items():
        lines.append(f"export {k}={v!r}")
    example = _pick_example_url(services)
    if example:
        key = services[0].recommended_env_var if services else "SERVICE_URL"
        lines.extend(["", f'curl -sS "${{{key}}}"'])
    return "\n".join(lines) + "\n"


def _python_snippet(env: dict[str, str], services: list[IntegrationServiceOutput]) -> str:
    example = _pick_example_url(services)
    key = services[0].recommended_env_var if services else "SERVICE_URL"
    lines = [
        "import os",
        "import requests",
        "",
    ]
    if any(s.endpoint_scope == "internal_only" for s in services):
        lines.append(f"# Note: {INTERNAL_ONLY_NOTE}")
        lines.append("")
    lines.extend(
        [
            f"base_url = os.environ[{key!r}]",
            "response = requests.get(base_url, timeout=10)",
            "response.raise_for_status()",
            "print(response.text)",
        ]
    )
    if example:
        lines.insert(3, f"# Example: export {key}={example!r}")
    return "\n".join(lines) + "\n"


def _javascript_snippet(services: list[IntegrationServiceOutput]) -> str:
    example = _pick_example_url(services) or "http://127.0.0.1:8080"
    key = services[0].recommended_env_var if services else "API_SERVICE_URL"
    note = ""
    if any(s.endpoint_scope == "internal_only" for s in services):
        note = f"// {INTERNAL_ONLY_NOTE}\n"
    return (
        f"{note}"
        f"const baseUrl = process.env.{key} ?? {example!r};\n"
        "const res = await fetch(baseUrl);\n"
        "if (!res.ok) throw new Error(await res.text());\n"
        "console.log(await res.text());\n"
    )


def _typescript_snippet(services: list[IntegrationServiceOutput]) -> str:
    example = _pick_example_url(services) or "http://127.0.0.1:8080"
    key = services[0].recommended_env_var if services else "API_SERVICE_URL"
    note = ""
    if any(s.endpoint_scope == "internal_only" for s in services):
        note = f"// {INTERNAL_ONLY_NOTE}\n"
    return (
        f"{note}"
        f"const baseUrl: string = process.env.{key} ?? {example!r};\n"
        "const res = await fetch(baseUrl);\n"
        "if (!res.ok) throw new Error(await res.text());\n"
        "const body: string = await res.text();\n"
        "console.log(body);\n"
    )


def _java_snippet(services: list[IntegrationServiceOutput]) -> str:
    example = _pick_example_url(services) or "http://127.0.0.1:8080"
    key = services[0].recommended_env_var if services else "API_SERVICE_URL"
    note = ""
    if any(s.endpoint_scope == "internal_only" for s in services):
        note = f"// {INTERNAL_ONLY_NOTE}\n"
    return (
        f"{note}"
        "import java.net.URI;\n"
        "import java.net.http.HttpClient;\n"
        "import java.net.http.HttpRequest;\n"
        "import java.net.http.HttpResponse;\n\n"
        f'String baseUrl = System.getenv("{key}");\n'
        "if (baseUrl == null) baseUrl = "
        f'"{example}";\n'
        "HttpClient client = HttpClient.newHttpClient();\n"
        "HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl)).GET().build();\n"
        "HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());\n"
        "System.out.println(response.body());\n"
    )


def _go_snippet(services: list[IntegrationServiceOutput]) -> str:
    example = _pick_example_url(services) or "http://127.0.0.1:8080"
    key = services[0].recommended_env_var if services else "API_SERVICE_URL"
    note = ""
    if any(s.endpoint_scope == "internal_only" for s in services):
        note = f"// {INTERNAL_ONLY_NOTE}\n"
    return (
        f"{note}"
        "package main\n\n"
        "import (\n"
        '\t"fmt"\n'
        '\t"io"\n'
        '\t"net/http"\n'
        '\t"os"\n'
        ")\n\n"
        "func main() {\n"
        f'\tbaseURL := os.Getenv("{key}")\n'
        "\tif baseURL == \"\" {\n"
        f'\t\tbaseURL = "{example}"\n'
        "\t}\n"
        "\tresp, err := http.Get(baseURL)\n"
        "\tif err != nil {\n"
        '\t\tpanic(err)\n'
        "\t}\n"
        "\tdefer resp.Body.Close()\n"
        "\tbody, _ := io.ReadAll(resp.Body)\n"
        '\tfmt.Println(string(body))\n'
        "}\n"
    )


def _ruby_snippet(services: list[IntegrationServiceOutput]) -> str:
    example = _pick_example_url(services) or "http://127.0.0.1:8080"
    key = services[0].recommended_env_var if services else "API_SERVICE_URL"
    note = ""
    if any(s.endpoint_scope == "internal_only" for s in services):
        note = f"# {INTERNAL_ONLY_NOTE}\n"
    return (
        f"{note}"
        "require 'net/http'\n"
        "require 'uri'\n\n"
        f'base_url = ENV.fetch("{key}", "{example}")\n'
        "uri = URI(base_url)\n"
        "response = Net::HTTP.get_response(uri)\n"
        "raise response.body unless response.is_a?(Net::HTTPSuccess)\n"
        "puts response.body\n"
    )


def _php_snippet(services: list[IntegrationServiceOutput]) -> str:
    example = _pick_example_url(services) or "http://127.0.0.1:8080"
    key = services[0].recommended_env_var if services else "API_SERVICE_URL"
    note = ""
    if any(s.endpoint_scope == "internal_only" for s in services):
        note = f"// {INTERNAL_ONLY_NOTE}\n"
    return (
        f"{note}"
        "<?php\n"
        f'$baseUrl = getenv("{key}") ?: "{example}";\n'
        "$ch = curl_init($baseUrl);\n"
        "curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);\n"
        "$body = curl_exec($ch);\n"
        "if ($body === false) {\n"
        '    throw new RuntimeException(curl_error($ch));\n'
        "}\n"
        "curl_close($ch);\n"
        "echo $body;\n"
    )


def _csharp_snippet(services: list[IntegrationServiceOutput]) -> str:
    example = _pick_example_url(services) or "http://127.0.0.1:8080"
    key = services[0].recommended_env_var if services else "API_SERVICE_URL"
    note = ""
    if any(s.endpoint_scope == "internal_only" for s in services):
        note = f"// {INTERNAL_ONLY_NOTE}\n"
    return (
        f"{note}"
        "using System;\n"
        "using System.Net.Http;\n\n"
        f'var baseUrl = Environment.GetEnvironmentVariable("{key}") ?? "{example}";\n'
        "using var client = new HttpClient();\n"
        "var body = await client.GetStringAsync(baseUrl);\n"
        "Console.WriteLine(body);\n"
    )


def _github_actions_snippet(
    *,
    dep_id: UUID,
    topo_id: UUID,
    env: dict[str, str],
    services: list[IntegrationServiceOutput],
    api_base: str,
) -> str:
    example_key = services[0].recommended_env_var if services else "API_SERVICE_URL"
    example_val = env.get(example_key, "")
    return (
        "name: cns-integration-test\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "env:\n"
        "  CNS_API: https://your-cns-host.example.com/api\n"
        "  CNS_TOKEN: ${{ secrets.CNS_TOKEN }}\n"
        f"  CNS_DEPLOYMENT_ID: {dep_id}\n"
        f"  CNS_TOPOLOGY_ID: {topo_id}\n"
        f"  {example_key}: '{example_val}'\n"
        "jobs:\n"
        "  integration:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - name: Verify CNS service URL\n"
        f"        run: curl -sf \"${{{{ env.{example_key} }}}}\"\n"
        "      - name: Run your project tests\n"
        "        run: pytest tests/integration -q\n"
        "      - name: Destroy CNS deployment (optional cleanup)\n"
        "        if: always()\n"
        "        run: |\n"
        '          curl -sS -X POST "$CNS_API/deployments/$CNS_DEPLOYMENT_ID/destroy" \\\n'
        '            -H "Authorization: Bearer $CNS_TOKEN"\n'
        "# Deploy fresh topology:\n"
        f"# curl -sS -X POST \"$CNS_API/topologies/{topo_id}/deploy\" -H \"Authorization: Bearer $CNS_TOKEN\"\n"
    )


def _docker_compose_snippet(env: dict[str, str], services: list[IntegrationServiceOutput]) -> str:
    env_lines = _env_snippet(env, services).strip().splitlines()
    dot_env = "\n".join(line for line in env_lines if not line.startswith("#")) + "\n"
    compose = [
        "# Add to your docker-compose.yml:",
        "services:",
        "  your-app:",
        "    image: your-app:latest",
        "    env_file:",
        "      - ./cns-deployment.env",
        "    # or inline:",
        "    environment:",
    ]
    for k, v in env.items():
        compose.append(f"      {k}: {v!r}")
    return "\n".join(compose) + "\n\n# ./cns-deployment.env\n" + dot_env


def _kubernetes_configmap_snippet(
    *,
    dep_id: UUID,
    topo_id: UUID,
    env: dict[str, str],
    services: list[IntegrationServiceOutput],
) -> str:
    lines = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        "  name: cns-deployment-outputs",
        "  labels:",
        "    app.kubernetes.io/managed-by: cloud-networking-studio",
        f"    cns.deployment_id: {dep_id}",
        f"    cns.topology_id: {topo_id}",
        "data:",
    ]
    if not env:
        lines.append("  # No service URLs yet")
    for k, v in env.items():
        lines.append(f"  {k}: {v!r}")
    if any(s.endpoint_scope == "internal_only" for s in services):
        lines.extend(
            [
                "  CNS_INTERNAL_ENDPOINT_NOTE: "
                f"{INTERNAL_ONLY_NOTE!r}",
            ]
        )
    return "\n".join(lines) + "\n"


def build_integration_outputs_bundle(
    *,
    env: dict[str, str],
    services: list[IntegrationServiceOutput],
    dep_id: UUID,
    topo_id: UUID,
    api_base: str = "/api",
) -> IntegrationOutputsBundle:
    return IntegrationOutputsBundle(
        env=_env_snippet(env, services),
        curl=_curl_snippet(services),
        bash=_bash_snippet(env, services),
        python=_python_snippet(env, services),
        javascript=_javascript_snippet(services),
        typescript=_typescript_snippet(services),
        java=_java_snippet(services),
        go=_go_snippet(services),
        ruby=_ruby_snippet(services),
        php=_php_snippet(services),
        csharp=_csharp_snippet(services),
        github_actions=_github_actions_snippet(
            dep_id=dep_id, topo_id=topo_id, env=env, services=services, api_base=api_base
        ),
        docker_compose_env=_docker_compose_snippet(env, services),
        kubernetes_configmap=_kubernetes_configmap_snippet(
            dep_id=dep_id, topo_id=topo_id, env=env, services=services
        ),
    )


def build_deployment_integration_outputs(
    session: Session, deployment_id: UUID, *, api_base: str = "/api"
) -> DeploymentIntegrationOutputsResponse:
    snap = build_deployment_runtime(session, deployment_id)
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = session.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")

    resources = [resource_row_to_public_dict(r) for r in list_runtime_resources(session, deployment_id)]
    exposures = [exposure_to_api_dict(e) for e in list_exposure_rows(session, deployment_id)]
    services = _catalog_services(resources, exposures)
    env = _merged_env(services, dep.id, topo.id)
    outputs = build_integration_outputs_bundle(
        env=env,
        services=services,
        dep_id=dep.id,
        topo_id=topo.id,
        api_base=api_base,
    )

    return DeploymentIntegrationOutputsResponse(
        deployment_id=dep.id,
        topology_id=topo.id,
        runtime_provider=snap.runtime_provider,
        namespace_or_network=snap.namespace_or_network,
        services=services,
        outputs=outputs,
        metadata={
            "output_languages": list(OUTPUT_LANGUAGE_KEYS),
            "internal_only_note": INTERNAL_ONLY_NOTE,
            "api_endpoint": f"{api_base}/deployments/{dep.id}/integration-outputs",
            "topology_version_id": str(dep.topology_version_id) if dep.topology_version_id else None,
            "deployment_profile_id": str(dep.deployment_profile_id) if dep.deployment_profile_id else None,
        },
    )


def normalize_integration_filename(file_name: str) -> str:
    """Return basename only; reject path traversal."""
    raw = (file_name or "").strip()
    if not raw or raw != file_name.strip():
        raise ValueError("invalid file name")
    if "/" in raw or "\\" in raw or ".." in raw:
        raise ValueError("invalid file name")
    return raw.split("/")[-1].split("\\")[-1]


def resolve_integration_file_spec(file_name: str) -> IntegrationOutputFileSpec:
    normalized = normalize_integration_filename(file_name)
    spec = INTEGRATION_FILES_BY_NAME.get(normalized)
    if spec is None:
        raise LookupError("file not found")
    return spec


def _file_content(outputs: IntegrationOutputsBundle, spec: IntegrationOutputFileSpec) -> str:
    data = outputs.model_dump()
    content = data.get(spec.output_key, "")
    return str(content) if content is not None else ""


def build_integration_output_file_manifest(
    deployment_id: UUID, *, api_base: str = "/api"
) -> list[IntegrationOutputFileItem]:
    base = f"{api_base}/deployments/{deployment_id}/integration-outputs/files"
    return [
        IntegrationOutputFileItem(
            name=spec.name,
            type=spec.type,
            download_url=f"{base}/{spec.name}",
        )
        for spec in INTEGRATION_OUTPUT_FILE_SPECS
    ]


def get_integration_output_file(
    session: Session, deployment_id: UUID, file_name: str, *, api_base: str = "/api"
) -> tuple[IntegrationOutputFileSpec, str]:
    spec = resolve_integration_file_spec(file_name)
    body = build_deployment_integration_outputs(session, deployment_id, api_base=api_base)
    return spec, _file_content(body.outputs, spec)


def build_integration_outputs_archive(
    session: Session, deployment_id: UUID, *, api_base: str = "/api"
) -> bytes:
    body = build_deployment_integration_outputs(session, deployment_id, api_base=api_base)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for spec in INTEGRATION_OUTPUT_FILE_SPECS:
            zf.writestr(spec.name, _file_content(body.outputs, spec))
    return buf.getvalue()
