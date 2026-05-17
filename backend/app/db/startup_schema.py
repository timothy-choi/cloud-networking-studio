"""Register all ORM tables on ``Base.metadata`` and validate core DDL after ``create_all``.

Call :func:`import_all_orm_modules` before :func:`sqlalchemy.schema.MetaData.create_all`
so every model (users, projects, topologies, …) is present. Partial imports were a
real foot-gun: ``create_all`` would omit ``users`` while auth routes assumed it existed.
"""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

_SCHEMA_RECREATE_HINT = (
    "If you recently changed auth/project/topology models, local Postgres may still "
    "use an old volume layout. Recreate the database volume and stack:\n"
    "  docker compose down -v\n"
    "  docker compose up -d --build\n"
    "(or the same with ``docker compose -f docker-compose.prod.yml …``.)"
)


def import_all_orm_modules() -> None:
    """Import every ORM module so all tables are registered on ``Base.metadata``.

    Loads ``app.models`` (package ``__init__``) plus each submodule explicitly so
    refactors cannot drop a table from metadata while the package still imports.
    """
    import app.models  # noqa: F401 — package barrel

    import app.models.deployment  # noqa: F401
    import app.models.deployment_runtime_resource  # noqa: F401
    import app.models.deployment_runtime_exec_result  # noqa: F401
    import app.models.deployment_service_exposure  # noqa: F401
    import app.models.failure_injection  # noqa: F401
    import app.models.project  # noqa: F401
    import app.models.project_membership  # noqa: F401
    import app.models.topology  # noqa: F401
    import app.models.traffic_test  # noqa: F401
    import app.models.user  # noqa: F401


def verify_core_schema(engine: Engine) -> None:
    """Assert auth/project/topology DDL exists after ``create_all``.

    Raises ``RuntimeError`` with an actionable message (including volume reset) if
    the database is missing expected tables or columns — avoids silent reliance on
    stale Docker volumes.
    """
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    required = ("users", "projects", "project_memberships", "topologies")
    missing_tables = [t for t in required if t not in tables]
    if missing_tables:
        raise RuntimeError(
            "Database schema is missing required table(s): "
            f"{', '.join(missing_tables)}. "
            "The API cannot start without them.\n"
            + _SCHEMA_RECREATE_HINT
        )

    topo_cols = {c["name"] for c in insp.get_columns("topologies")}
    if "project_id" not in topo_cols:
        raise RuntimeError(
            "Table `topologies` exists but is missing the `project_id` column "
            "(expected after project scoping). The API cannot start.\n"
            + _SCHEMA_RECREATE_HINT
        )
