"""Orchestrate ping / HTTP traffic tests against runtime containers."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel
from app.models.topology import Topology, TopologyNode
from app.models.traffic_test import TrafficTest, TrafficTestResult, TrafficTestStatus, TrafficTestType
from app.providers.docker_runtime_provider import runtime_provider_for_topology


_CLAMP_COUNT = (1, 10)
_CLAMP_PORT = (1, 65535)

_SAFE_HTTP_PATH = re.compile(r"^/[A-Za-z0-9._/\-]*$")


def _latest_deployment_id(session: Session, topology_id: UUID) -> UUID | None:
    stmt = (
        select(Deployment.id)
        .where(Deployment.topology_id == topology_id)
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    row = session.execute(stmt).scalar_one_or_none()
    return row


def _emit_deployment_event(
    session: Session,
    deployment_id: UUID | None,
    level: DeploymentEventLevel,
    message: str,
) -> None:
    if deployment_id is None:
        return
    session.add(
        DeploymentEvent(
            deployment_id=deployment_id,
            level=level,
            message=message,
        )
    )


def _validate_topology_node(
    session: Session, topology_id: UUID, node_id: UUID
) -> TopologyNode:
    node = session.get(TopologyNode, node_id)
    if node is None or node.topology_id != topology_id:
        raise LookupError("node not found")
    return node


def _parse_ping_latency_ms(stdout: str) -> float | None:
    m = re.search(r"time[=<]([\d.]+)\s*ms", stdout, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _build_ping_argv(target_ip: str, count: int) -> list[str]:
    c = max(_CLAMP_COUNT[0], min(int(count), _CLAMP_COUNT[1]))
    return ["ping", "-c", str(c), "-W", "2", target_ip]


def _build_http_argv(target_ip: str, port: int, path: str) -> list[str]:
    p = max(_CLAMP_PORT[0], min(int(port), _CLAMP_PORT[1]))
    if not _SAFE_HTTP_PATH.match(path):
        raise ValueError("path contains disallowed characters")
    url = f"http://{target_ip}:{p}{path}"
    return ["wget", "-q", "-O-", "-T", "10", url]


def run_ping_test(
    session: Session,
    topology_id: UUID,
    source_node_id: UUID,
    target_node_id: UUID,
    count: int = 3,
) -> TrafficTest:
    topo = session.get(Topology, topology_id)
    if topo is None:
        raise LookupError("topology not found")

    src = _validate_topology_node(session, topology_id, source_node_id)
    tgt = _validate_topology_node(session, topology_id, target_node_id)

    deployment_id = _latest_deployment_id(session, topology_id)
    provider = runtime_provider_for_topology(topo.runtime_target)
    count_clamped = max(_CLAMP_COUNT[0], min(int(count), _CLAMP_COUNT[1]))

    tt = TrafficTest(
        topology_id=topology_id,
        deployment_id=deployment_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        test_type=TrafficTestType.PING,
        status=TrafficTestStatus.PENDING,
        command="(pending)",
    )
    session.add(tt)
    session.flush()

    _emit_deployment_event(
        session,
        deployment_id,
        DeploymentEventLevel.INFO,
        f"Traffic test started: ping {src.name} -> {tgt.name}",
    )

    tt.status = TrafficTestStatus.RUNNING
    tt.started_at = datetime.now(UTC)

    target_ip = provider.resolve_node_ipv4(topology_id, target_node_id, source_node_id)
    argv = _build_ping_argv(target_ip or "0.0.0.0", count_clamped)
    tt.command = " ".join(argv)

    if target_ip is None:
        tt.status = TrafficTestStatus.FAILED
        tt.finished_at = datetime.now(UTC)
        tr = TrafficTestResult(
            traffic_test_id=tt.id,
            exit_code=1,
            stdout="",
            stderr=(
                "could not resolve IPv4 on the CNS topology network "
                "(default bridge addresses are not used for traffic tests)"
            ),
            latency_ms=None,
            success=False,
        )
        session.add(tr)
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.WARNING,
            "Traffic test failed: no CNS topology network IPv4 for target (not using 172.17.x)",
        )
        session.flush()
        return tt

    ex = provider.exec_in_node_container(topology_id, source_node_id, argv)
    tt.finished_at = datetime.now(UTC)

    if ex is None:
        tt.status = TrafficTestStatus.FAILED
        tr = TrafficTestResult(
            traffic_test_id=tt.id,
            exit_code=127,
            stdout="",
            stderr="source node runtime container not found",
            latency_ms=None,
            success=False,
        )
        session.add(tr)
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.WARNING,
            "Traffic test failed: source container missing",
        )
        session.flush()
        return tt

    lat = _parse_ping_latency_ms(ex.stdout) if ex.exit_code == 0 else None
    ok = ex.exit_code == 0
    tt.status = TrafficTestStatus.SUCCEEDED if ok else TrafficTestStatus.FAILED
    tr = TrafficTestResult(
        traffic_test_id=tt.id,
        exit_code=ex.exit_code,
        stdout=ex.stdout,
        stderr=ex.stderr,
        latency_ms=lat,
        success=ok,
    )
    session.add(tr)
    if ok:
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.INFO,
            "Traffic test succeeded",
        )
    else:
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.WARNING,
            "Traffic test failed",
        )
    session.flush()
    return tt


def run_http_test(
    session: Session,
    topology_id: UUID,
    source_node_id: UUID,
    target_node_id: UUID,
    path: str = "/",
    port: int = 80,
) -> TrafficTest:
    topo = session.get(Topology, topology_id)
    if topo is None:
        raise LookupError("topology not found")

    src = _validate_topology_node(session, topology_id, source_node_id)
    tgt = _validate_topology_node(session, topology_id, target_node_id)

    try:
        _build_http_argv("127.0.0.1", port, path)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    deployment_id = _latest_deployment_id(session, topology_id)
    provider = runtime_provider_for_topology(topo.runtime_target)

    tt = TrafficTest(
        topology_id=topology_id,
        deployment_id=deployment_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        test_type=TrafficTestType.HTTP,
        status=TrafficTestStatus.PENDING,
        command="(pending)",
    )
    session.add(tt)
    session.flush()

    _emit_deployment_event(
        session,
        deployment_id,
        DeploymentEventLevel.INFO,
        f"HTTP traffic test started: {src.name} -> {tgt.name} port={port} path={path}",
    )

    tt.status = TrafficTestStatus.RUNNING
    tt.started_at = datetime.now(UTC)

    target_ip = provider.resolve_node_ipv4(topology_id, target_node_id, source_node_id)
    if target_ip is None:
        tt.status = TrafficTestStatus.FAILED
        tt.finished_at = datetime.now(UTC)
        tt.command = f"(missing target IPv4) wget http://<target>:{port}{path}"
        session.add(
            TrafficTestResult(
                traffic_test_id=tt.id,
                exit_code=1,
                stdout="",
                stderr=(
                    "could not resolve IPv4 on the CNS topology network "
                    "(default bridge addresses are not used for traffic tests)"
                ),
                latency_ms=None,
                success=False,
            )
        )
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.WARNING,
            "HTTP traffic test failed: no CNS topology network IPv4 for target (not using 172.17.x)",
        )
        session.flush()
        return tt

    argv = _build_http_argv(target_ip, port, path)
    tt.command = " ".join(argv)

    ex = provider.exec_in_node_container(topology_id, source_node_id, argv)
    tt.finished_at = datetime.now(UTC)

    if ex is None:
        tt.status = TrafficTestStatus.FAILED
        session.add(
            TrafficTestResult(
                traffic_test_id=tt.id,
                exit_code=127,
                stdout="",
                stderr="source node runtime container not found",
                latency_ms=None,
                success=False,
            )
        )
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.WARNING,
            "HTTP traffic test failed: source container missing",
        )
        session.flush()
        return tt

    ok = ex.exit_code == 0
    tt.status = TrafficTestStatus.SUCCEEDED if ok else TrafficTestStatus.FAILED
    session.add(
        TrafficTestResult(
            traffic_test_id=tt.id,
            exit_code=ex.exit_code,
            stdout=ex.stdout,
            stderr=ex.stderr,
            latency_ms=None,
            success=ok,
        )
    )
    _emit_deployment_event(
        session,
        deployment_id,
        DeploymentEventLevel.INFO,
        "HTTP traffic test result recorded",
    )
    if ok:
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.INFO,
            "HTTP traffic test succeeded",
        )
    else:
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.WARNING,
            "HTTP traffic test failed",
        )
    session.flush()
    return tt


def get_traffic_test(session: Session, traffic_test_id: UUID) -> TrafficTest | None:
    stmt = (
        select(TrafficTest)
        .where(TrafficTest.id == traffic_test_id)
        .options(selectinload(TrafficTest.result))
    )
    return session.execute(stmt).scalar_one_or_none()


def list_traffic_tests_for_topology(
    session: Session, topology_id: UUID
) -> list[TrafficTest]:
    stmt = (
        select(TrafficTest)
        .where(TrafficTest.topology_id == topology_id)
        .options(selectinload(TrafficTest.result))
        .order_by(TrafficTest.created_at.desc())
    )
    return list(session.scalars(stmt).all())
