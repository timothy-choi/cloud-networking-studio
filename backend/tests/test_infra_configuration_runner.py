"""Tests for post-apply configuration job scheduling."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services import infra_configuration_runner as runner


def _deployment(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "status": "configuring",
        "state_metadata_json": {"configuration_job_status": "queued"},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_deployment_has_queued_configuration():
    assert runner.deployment_has_queued_configuration(_deployment()) is True
    assert (
        runner.deployment_has_queued_configuration(
            _deployment(state_metadata_json={"configuration_job_status": "running"})
        )
        is False
    )
    assert runner.deployment_has_queued_configuration(_deployment(status="succeeded")) is False


def test_schedule_host_configuration_deferred_uses_background_tasks(monkeypatch):
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def fake_enqueue(*, deployment_id, actor_user_id):
        calls.append((deployment_id, actor_user_id))
        return True

    scheduled: list[tuple[object, tuple, dict]] = []

    class FakeBackgroundTasks:
        def add_task(self, fn, *args, **kwargs):
            scheduled.append((fn, args, kwargs))

    monkeypatch.delenv("CNS_SYNC_INFRA_CONFIGURATION", raising=False)
    monkeypatch.setattr(runner, "enqueue_host_configuration", fake_enqueue)

    dep_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    tasks = FakeBackgroundTasks()
    runner.schedule_host_configuration(
        deployment_id=dep_id,
        actor_user_id=actor_id,
        background_tasks=tasks,
    )

    assert len(scheduled) == 1
    fn, args, kwargs = scheduled[0]
    assert fn is fake_enqueue
    assert args == ()
    assert kwargs == {"deployment_id": dep_id, "actor_user_id": actor_id}
    assert calls == []


def test_schedule_host_configuration_sync_runs_inline(monkeypatch):
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def fake_enqueue(*, deployment_id, actor_user_id):
        calls.append((deployment_id, actor_user_id))
        return True

    monkeypatch.setenv("CNS_SYNC_INFRA_CONFIGURATION", "1")
    monkeypatch.setattr(runner, "enqueue_host_configuration", fake_enqueue)

    dep_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    runner.schedule_host_configuration(
        deployment_id=dep_id,
        actor_user_id=actor_id,
        background_tasks=None,
    )

    assert calls == [(dep_id, actor_id)]
