"""ORM models — import order registers all tables on ``Base.metadata``.

Application startup and tests should call ``import_all_orm_modules()`` from
``app.db.startup_schema`` before ``Base.metadata.create_all()`` so every table
(including ``users``) is registered even if only a subset of routers was imported.
"""

# Users and projects before topology FKs.
from app.models.project import Project
from app.models.project_invitation import ProjectInvitation
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.models.user_onboarding import UserOnboarding

# Topology graph entities before deployment FKs.
from app.models.topology import (
    NodeType,
    Topology,
    TopologyLink,
    TopologyNode,
    TopologyStatus,
)
from app.models.notification import Notification
from app.models.audit_log import AuditLog
from app.models.deployment_timeline import DeploymentTimelineEvent, TimelineEventType
from app.models.deployment import (
    Deployment,
    DeploymentEvent,
    DeploymentEventLevel,
    DeploymentStatus,
    TopologySyncStatus,
)
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_runtime_exec_result import DeploymentRuntimeExecResult
from app.models.deployment_runtime_terminal_session import DeploymentRuntimeTerminalSession
from app.models.deployment_service_exposure import DeploymentServiceExposure
from app.models.deployment_profile import DeploymentProfile
from app.models.topology_version import TopologyVersion
from app.models.traffic_test import TrafficTest, TrafficTestResult, TrafficTestStatus, TrafficTestType
from app.models.failure_injection import (
    FailureInjection,
    FailureInjectionFailureType,
    FailureInjectionStatus,
)
from app.models.runtime_template import RuntimeTemplate, TemplateVisibility

__all__ = [
    "Notification",
    "ApiToken",
    "AuditLog",
    "DeploymentTimelineEvent",
    "TimelineEventType",
    "Deployment",
    "DeploymentRuntimeExecResult",
    "DeploymentRuntimeTerminalSession",
    "DeploymentRuntimeResource",
    "DeploymentServiceExposure",
    "DeploymentProfile",
    "TopologyVersion",
    "DeploymentEvent",
    "DeploymentEventLevel",
    "DeploymentStatus",
    "TopologySyncStatus",
    "FailureInjection",
    "FailureInjectionFailureType",
    "FailureInjectionStatus",
    "NodeType",
    "Project",
    "ProjectInvitation",
    "ProjectMembership",
    "RuntimeTemplate",
    "Topology",
    "TopologyLink",
    "TopologyNode",
    "TopologyStatus",
    "TemplateVisibility",
    "TrafficTest",
    "TrafficTestResult",
    "TrafficTestStatus",
    "TrafficTestType",
    "User",
    "UserOnboarding",
]
