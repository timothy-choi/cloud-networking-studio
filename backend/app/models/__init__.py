"""ORM models — import order registers all tables on ``Base.metadata``."""

# Topology first so graph entities exist before deployment FKs resolve at mapper config time.
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
    "Topology",
    "TopologyLink",
    "TopologyNode",
    "TopologyStatus",
    "TrafficTest",
    "TrafficTestResult",
    "TrafficTestStatus",
    "TrafficTestType",
]
