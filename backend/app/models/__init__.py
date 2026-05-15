"""ORM models — import order registers all tables on ``Base.metadata``."""

# Users and projects before topology FKs.
from app.models.project import Project
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
from app.models.traffic_test import TrafficTest, TrafficTestResult, TrafficTestStatus, TrafficTestType
from app.models.failure_injection import (
    FailureInjection,
    FailureInjectionFailureType,
    FailureInjectionStatus,
)

__all__ = [
    "Deployment",
    "DeploymentEvent",
    "DeploymentEventLevel",
    "DeploymentStatus",
    "FailureInjection",
    "FailureInjectionFailureType",
    "FailureInjectionStatus",
    "NodeType",
    "Project",
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
