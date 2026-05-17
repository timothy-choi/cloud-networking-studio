"""ORM models — import order registers all tables on ``Base.metadata``.

Application startup and tests should call ``import_all_orm_modules()`` from
``app.db.startup_schema`` before ``Base.metadata.create_all()`` so every table
(including ``users``) is registered even if only a subset of routers was imported.
"""

# Users and projects before topology FKs.
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.user import User

# Topology graph entities before deployment FKs.
from app.models.topology import (
    NodeType,
    Topology,
    TopologyLink,
    TopologyNode,
    TopologyStatus,
)
from app.models.deployment import (
    Deployment,
    DeploymentEvent,
    DeploymentEventLevel,
    DeploymentStatus,
)
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_service_exposure import DeploymentServiceExposure
from app.models.traffic_test import TrafficTest, TrafficTestResult, TrafficTestStatus, TrafficTestType
from app.models.failure_injection import (
    FailureInjection,
    FailureInjectionFailureType,
    FailureInjectionStatus,
)

__all__ = [
    "Deployment",
    "DeploymentRuntimeResource",
    "DeploymentServiceExposure",
    "DeploymentEvent",
    "DeploymentEventLevel",
    "DeploymentStatus",
    "FailureInjection",
    "FailureInjectionFailureType",
    "FailureInjectionStatus",
    "NodeType",
    "Project",
    "ProjectMembership",
    "Topology",
    "TopologyLink",
    "TopologyNode",
    "TopologyStatus",
    "TrafficTest",
    "TrafficTestResult",
    "TrafficTestStatus",
    "TrafficTestType",
    "User",
]
