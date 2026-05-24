"""API tokens and Bearer auth (Step 44, scopes Step 53D)."""

from __future__ import annotations

import uuid

from sqlalchemy import inspect, text


def _reg(client_strict, prefix: str) -> tuple[str, dict[str, str], str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    user_id = client_strict.get("/auth/me", headers=headers).json()["user"]["id"]
    return email, headers, user_id


def _assert_list_item_safe(item: dict) -> None:
    assert "token_hash" not in item
    assert "token" not in item
    for key in item:
        assert "secret" not in key.lower()
        assert "hash" not in key.lower()


def test_api_token_create_list_revoke(client_strict):
    _, h, _ = _reg(client_strict, "tok")
    cr = client_strict.post("/api-tokens", headers=h, json={"name": "ci"})
    assert cr.status_code == 201, cr.text
    body = cr.json()
    assert "token" in body and "." in body["token"]
    tid = body["id"]
    lst = client_strict.get("/api-tokens", headers=h)
    assert lst.status_code == 200
    listed = next(x for x in lst.json() if x["id"] == tid)
    _assert_list_item_safe(listed)

    raw = body["token"]
    hp = {"Authorization": f"Bearer {raw}"}
    me = client_strict.get("/auth/me", headers=hp)
    assert me.status_code == 200, me.text

    pr = client_strict.get("/projects", headers=hp)
    assert pr.status_code == 200, pr.text

    assert client_strict.delete(f"/api-tokens/{tid}", headers=h).status_code == 204

    fail = client_strict.get("/projects", headers=hp)
    assert fail.status_code == 401


def test_second_token_still_works_after_revoking_first(client_strict):
    _, h, _ = _reg(client_strict, "tok2")
    first = client_strict.post("/api-tokens", headers=h, json={"name": "a"}).json()
    second = client_strict.post("/api-tokens", headers=h, json={"name": "b"}).json()
    assert client_strict.delete(f"/api-tokens/{first['id']}", headers=h).status_code == 204
    assert client_strict.get("/auth/me", headers={"Authorization": f"Bearer {second['token']}"}).status_code == 200


def test_list_legacy_token_null_scopes_json(client_strict, engine_db):
    from app.core.security import hash_api_token_secret
    from app.db.session import SessionLocal
    from app.models.api_token import ApiToken

    _, h, user_id = _reg(client_strict, "leg")
    with SessionLocal() as db:
        row = ApiToken(
            user_id=uuid.UUID(user_id),
            name="legacy-row",
            token_hash=hash_api_token_secret("legacy-secret-value"),
            token_hint="alue",
            scopes_json=None,
        )
        db.add(row)
        db.commit()
        legacy_id = row.id

    lst = client_strict.get("/api-tokens", headers=h)
    assert lst.status_code == 200, lst.text
    item = next(x for x in lst.json() if x["id"] == str(legacy_id))
    assert item["name"] == "legacy-row"
    assert item["scopes"] is None
    _assert_list_item_safe(item)


def test_list_scoped_token(client_strict):
    _, h, _ = _reg(client_strict, "scoped")
    cr = client_strict.post(
        "/api-tokens",
        headers=h,
        json={"name": "read-only", "scopes": ["read:projects"]},
    )
    assert cr.status_code == 201, cr.text
    tid = cr.json()["id"]

    lst = client_strict.get("/api-tokens", headers=h)
    assert lst.status_code == 200, lst.text
    item = next(x for x in lst.json() if x["id"] == tid)
    assert item["scopes"] == ["read:projects"]
    _assert_list_item_safe(item)


def test_get_api_tokens_never_returns_hash_or_plaintext(client_strict):
    _, h, _ = _reg(client_strict, "sec")
    created = client_strict.post("/api-tokens", headers=h, json={"name": "visible-once"}).json()
    lst = client_strict.get("/api-tokens", headers=h)
    assert lst.status_code == 200
    for item in lst.json():
        _assert_list_item_safe(item)
    assert created["token"] not in str(lst.json())


def _reset_alembic_revision(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_alembic_skips_when_api_tokens_table_missing(engine_db):
    from alembic import command
    from alembic.config import Config
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS api_tokens CASCADE"))
    _reset_alembic_revision(engine)

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    command.upgrade(cfg, "head")

    insp = inspect(engine)
    assert "api_tokens" not in insp.get_table_names()


def test_alembic_skips_project_invitations_when_core_tables_missing(engine_db):
    from alembic import command
    from alembic.config import Config
    from app.db.session import Base, engine
    from app.db.startup_schema import import_all_orm_modules

    import_all_orm_modules()
    Base.metadata.drop_all(bind=engine)
    _reset_alembic_revision(engine)

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    command.upgrade(cfg, "head")

    insp = inspect(engine)
    assert "project_invitations" not in insp.get_table_names()


def test_alembic_adds_project_invitations_when_core_tables_exist(engine_db):
    from alembic import command
    from alembic.config import Config
    from app.db.session import Base, engine
    from app.db.startup_schema import import_all_orm_modules, verify_core_schema

    import_all_orm_modules()
    Base.metadata.create_all(bind=engine)
    verify_core_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS project_invitations CASCADE"))
    _reset_alembic_revision(engine)

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    command.upgrade(cfg, "head")

    tables = inspect(engine).get_table_names()
    assert "project_invitations" in tables


def test_alembic_adds_scopes_json_column(client_strict, engine_db):
    from alembic import command
    from alembic.config import Config
    from app.core.security import hash_api_token_secret
    from app.db.session import SessionLocal, engine
    from app.models.api_token import ApiToken

    insp = inspect(engine)
    cols_before = {c["name"] for c in insp.get_columns("api_tokens")}
    with engine.begin() as conn:
        if "scopes_json" in cols_before:
            conn.execute(text("ALTER TABLE api_tokens DROP COLUMN scopes_json"))
    _reset_alembic_revision(engine)

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    command.upgrade(cfg, "head")

    cols_after = {c["name"] for c in inspect(engine).get_columns("api_tokens")}
    assert "scopes_json" in cols_after

    _, h, user_id = _reg(client_strict, "mig")
    with SessionLocal() as db:
        row = ApiToken(
            user_id=uuid.UUID(user_id),
            name="post-migration",
            token_hash=hash_api_token_secret("after-migrate"),
            token_hint="rate",
            scopes_json=None,
        )
        db.add(row)
        db.commit()

    lst = client_strict.get("/api-tokens", headers=h)
    assert lst.status_code == 200, lst.text
    assert any(x["name"] == "post-migration" for x in lst.json())

