"""Execute controlled runtime failures for resilience experiments."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel
from app.models.failure_injection import (
    FailureInjection,
    FailureInjectionFailureType,
    FailureInjectionStatus,
)
from app.models.topology import Topology, TopologyNode
from app.providers.docker_runtime_provider import runtime_provider_for_topology


def _latest_deployment_id(session: Session, topology_id: UUID) -> UUID | None:
    stmt = (
        select(Deployment.id)
        .where(Deployment.topology_id == topology_id)
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


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


_ACTION_LABEL: dict[FailureInjectionFailureType, str] = {
    FailureInjectionFailureType.STOP_CONTAINER: "stop-node",
    FailureInjectionFailureType.RESTART_CONTAINER: "restart-node",
    FailureInjectionFailureType.KILL_CONTAINER: "kill-node",
}

_SUCCESS_NODE_LINE: dict[FailureInjectionFailureType, str] = {
    FailureInjectionFailureType.STOP_CONTAINER: "Node container stopped",
    FailureInjectionFailureType.RESTART_CONTAINER: "Node container restarted",
    FailureInjectionFailureType.KILL_CONTAINER: "Node container killed",
}


def run_failure_injection(
    session: Session,
    topology_id: UUID,
    target_node_id: UUID,
    failure_type: FailureInjectionFailureType,
    description: str | None,
) -> FailureInjection:
    topo = session.get(Topology, topology_id)
    if topo is None:
        raise LookupError("topology not found")

    node = _validate_topology_node(session, topology_id, target_node_id)
    deployment_id = _latest_deployment_id(session, topology_id)

    fi = FailureInjection(
        topology_id=topology_id,
        deployment_id=deployment_id,
        target_node_id=target_node_id,
        failure_type=failure_type,
        status=FailureInjectionStatus.PENDING,
        description=description,
    )
    session.add(fi)
    session.flush()

    action = _ACTION_LABEL[failure_type]
    _emit_deployment_event(
        session,
        deployment_id,
        DeploymentEventLevel.INFO,
        f"Failure injection started: {action} {node.name}",
    )

    provider = runtime_provider_for_topology(topo.runtime_target)

    container_id = provider.find_container_id_for_node(topology_id, target_node_id)
    if container_id is None:
        fi.status = FailureInjectionStatus.FAILED
        fi.finished_at = datetime.utcnow()
        fi.result_message = (
            "runtime container not found for node (no matching engine workload)"
        )
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.WARNING,
            "Failure injection failed: no runtime container for target node",
        )
        session.flush()
        return fi

    fi.status = FailureInjectionStatus.RUNNING
    fi.started_at = datetime.utcnow()
    session.flush()

    try:
        if failure_type == FailureInjectionFailureType.STOP_CONTAINER:
            provider.stop_node_container(topology_id, target_node_id)
        elif failure_type == FailureInjectionFailureType.RESTART_CONTAINER:
            provider.restart_node_container(topology_id, target_node_id)
        elif failure_type == FailureInjectionFailureType.KILL_CONTAINER:
            provider.kill_node_container(topology_id, target_node_id)
        else:
            raise ValueError(f"unsupported failure type: {failure_type!r}")

        fi.status = FailureInjectionStatus.SUCCEEDED
        fi.finished_at = datetime.utcnow()
        fi.result_message = None
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.INFO,
            "Failure injection succeeded",
        )
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.INFO,
            _SUCCESS_NODE_LINE[failure_type],
        )
    except LookupError as exc:
        fi.status = FailureInjectionStatus.FAILED
        fi.finished_at = datetime.utcnow()
        fi.result_message = str(exc)
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.ERROR,
            f"Failure injection failed: {exc}",
        )
    except Exception as exc:
        fi.status = FailureInjectionStatus.FAILED
        fi.finished_at = datetime.utcnow()
        fi.result_message = str(exc)
        _emit_deployment_event(
            session,
            deployment_id,
            DeploymentEventLevel.ERROR,
            f"Failure injection failed: {exc}",
        )

    session.flush()
    return fi


def get_failure_injection(
    session: Session, failure_id: UUID
) -> FailureInjection | None:
    return session.get(FailureInjection, failure_id)


def list_failure_injections_for_topology(
    session: Session, topology_id: UUID
) -> list[FailureInjection]:
    stmt = (
        select(FailureInjection)
        .where(FailureInjection.topology_id == topology_id)
        .order_by(FailureInjection.created_at.desc())
    )
    return list(session.execute(stmt).scalars().all())
