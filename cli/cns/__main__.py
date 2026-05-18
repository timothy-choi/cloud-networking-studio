"""``python -m cli.cns`` — terminal and CI client for Cloud Networking Studio (Step 44)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from cli.cns.config import default_config_path, effective_base_url, effective_token, load_config, save_config
from cli.cns.http_client import ApiHttpError, request_json


def _out(data: Any, *, as_json: bool) -> None:
    if as_json or isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


def _url(base: str, path: str) -> str:
    b = base.rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{b}{p}"


def cmd_login(args: argparse.Namespace) -> int:
    base = effective_base_url(args.base_url)
    code, data = request_json(
        "POST",
        _url(base, "/auth/login"),
        token=None,
        body={"email": args.email, "password": args.password},
        timeout=30.0,
    )
    if code != 200 or not isinstance(data, dict) or "access_token" not in data:
        _out({"error": "login failed", "status": code, "body": data}, as_json=args.json)
        return 1
    cfg = load_config()
    cfg["api_base"] = base
    cfg["token"] = str(data["access_token"])
    save_config(cfg)
    if not args.json:
        print(f"Saved credentials to {default_config_path()}")
    _out({"ok": True, "api_base": base, "saved": True}, as_json=args.json)
    return 0


def cmd_token_set(args: argparse.Namespace) -> int:
    token = (args.token or "").strip()
    if not token and not sys.stdin.isatty():
        token = sys.stdin.read().strip()
    if not token:
        print("Usage: cns token set <token>  (or pipe token on stdin)", file=sys.stderr)
        return 1
    cfg = load_config()
    if args.base_url:
        cfg["api_base"] = args.base_url.strip().rstrip("/")
    cfg["token"] = token
    save_config(cfg)
    _out({"ok": True, "saved": True}, as_json=args.json)
    return 0


def _auth_headers(args: argparse.Namespace) -> tuple[str, str | None]:
    base = effective_base_url(args.base_url)
    tok = effective_token(args.token)
    return base, tok


def cmd_projects_list(args: argparse.Namespace) -> int:
    base, tok = _auth_headers(args)
    if not tok:
        print("No token: run `cns login` or `cns token set` or set CNS_TOKEN", file=sys.stderr)
        return 1
    code, data = request_json("GET", _url(base, "/projects"), token=tok)
    _out(data, as_json=args.json)
    return 0 if code == 200 else 1


def cmd_topologies_list(args: argparse.Namespace) -> int:
    base, tok = _auth_headers(args)
    if not tok:
        print("No token", file=sys.stderr)
        return 1
    q = f"?project_id={args.project_id}" if getattr(args, "project_id", None) else ""
    code, data = request_json("GET", _url(base, f"/topologies{q}"), token=tok)
    _out(data, as_json=args.json)
    return 0 if code == 200 else 1


def cmd_templates_list(args: argparse.Namespace) -> int:
    base, tok = _auth_headers(args)
    if not tok:
        print("No token", file=sys.stderr)
        return 1
    code, data = request_json("GET", _url(base, "/templates"), token=tok)
    _out(data, as_json=args.json)
    return 0 if code == 200 else 1


def cmd_deploy(args: argparse.Namespace) -> int:
    base, tok = _auth_headers(args)
    if not tok:
        print("No token", file=sys.stderr)
        return 1
    tid: str | None = None
    if args.topology_id:
        tid = args.topology_id
    elif args.template_id:
        pid = args.project_id
        if not pid:
            _, plist = request_json("GET", _url(base, "/projects"), token=tok)
            if not isinstance(plist, list) or not plist:
                print("No project_id and could not infer from /projects", file=sys.stderr)
                return 1
            pid = str(plist[0]["id"])
        code, topo = request_json(
            "POST",
            _url(base, f"/templates/{args.template_id}/clone"),
            token=tok,
            body={"name": args.name or None, "project_id": pid},
            timeout=120.0,
        )
        if code != 201 or not isinstance(topo, dict):
            _out({"error": "clone failed", "status": code, "body": topo}, as_json=args.json)
            return 1
        tid = str(topo["id"])
    else:
        print("Specify --topology-id or --template-id", file=sys.stderr)
        return 1
    code, dep = request_json("POST", _url(base, f"/topologies/{tid}/deploy"), token=tok, timeout=600.0)
    _out(dep, as_json=args.json)
    return 0 if code == 201 else 1


def cmd_wait(args: argparse.Namespace) -> int:
    base, tok = _auth_headers(args)
    if not tok:
        print("No token", file=sys.stderr)
        return 1
    deadline = time.monotonic() + args.timeout
    last: Any = None
    while time.monotonic() < deadline:
        code, dep = request_json("GET", _url(base, f"/deployments/{args.deployment_id}"), token=tok, timeout=60.0)
        last = dep
        if code == 200 and isinstance(dep, dict):
            st = str(dep.get("status", "")).lower()
            if st in ("succeeded", "failed", "stopped"):
                _out(dep, as_json=args.json)
                return 0 if st == "succeeded" else 1
        time.sleep(args.interval)
    _out({"error": "timeout", "last": last}, as_json=args.json)
    return 1


def cmd_runtime(args: argparse.Namespace) -> int:
    base, tok = _auth_headers(args)
    if not tok:
        print("No token", file=sys.stderr)
        return 1
    code, data = request_json("GET", _url(base, f"/deployments/{args.deployment_id}/runtime"), token=tok, timeout=60.0)
    _out(data, as_json=args.json)
    return 0 if code == 200 else 1


def cmd_health_check(args: argparse.Namespace) -> int:
    base, tok = _auth_headers(args)
    if not tok:
        print("No token", file=sys.stderr)
        return 1
    code, data = request_json(
        "POST",
        _url(base, f"/deployments/{args.deployment_id}/runtime/services/{args.service_id}/health-check"),
        token=tok,
        body={},
        timeout=60.0,
    )
    _out(data, as_json=args.json)
    return 0 if code == 200 else 1


def cmd_destroy(args: argparse.Namespace) -> int:
    base, tok = _auth_headers(args)
    if not tok:
        print("No token", file=sys.stderr)
        return 1
    code, data = request_json(
        "POST",
        _url(base, f"/deployments/{args.deployment_id}/destroy"),
        token=tok,
        body={},
        timeout=300.0,
    )
    _out(data, as_json=args.json)
    return 0 if code == 200 else 1


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Print JSON")
    common.add_argument("--base-url", default=None, help="API root (CNS_API_BASE_URL / config)")
    common.add_argument("--token", default=None, help="Bearer (CNS_TOKEN / config)")

    p = argparse.ArgumentParser(prog="cns", description="Cloud Networking Studio CLI", parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)

    plogin = sub.add_parser("login", parents=[common], help="Save JWT from email/password")
    plogin.add_argument("--email", required=True)
    plogin.add_argument("--password", required=True)
    plogin.set_defaults(func=cmd_login)

    ptok = sub.add_parser("token", parents=[common], help="Manage stored token")
    ptok_sub = ptok.add_subparsers(dest="token_cmd", required=True)
    pset = ptok_sub.add_parser("set", parents=[common], help="Store API token or JWT")
    pset.add_argument("token", nargs="?", default="")
    pset.set_defaults(func=cmd_token_set)

    pp = sub.add_parser("projects", parents=[common], help="Projects")
    pp_sub = pp.add_subparsers(dest="projects_cmd", required=True)
    pp_list = pp_sub.add_parser("list", parents=[common])
    pp_list.set_defaults(func=cmd_projects_list)

    tp = sub.add_parser("topologies", parents=[common], help="Topologies")
    tp_sub = tp.add_subparsers(dest="topologies_cmd", required=True)
    tp_list = tp_sub.add_parser("list", parents=[common])
    tp_list.add_argument("--project-id", default=None)
    tp_list.set_defaults(func=cmd_topologies_list)

    tmpl = sub.add_parser("templates", parents=[common], help="Templates")
    tmpl_sub = tmpl.add_subparsers(dest="templates_cmd", required=True)
    tmpl_list = tmpl_sub.add_parser("list", parents=[common])
    tmpl_list.set_defaults(func=cmd_templates_list)

    dep = sub.add_parser("deploy", parents=[common], help="Deploy topology or clone template then deploy")
    dep.add_argument("--topology-id", default=None)
    dep.add_argument("--template-id", default=None)
    dep.add_argument("--project-id", default=None)
    dep.add_argument("--name", default=None)
    dep.set_defaults(func=cmd_deploy)

    w = sub.add_parser("wait", parents=[common], help="Wait for deployment terminal status")
    w.add_argument("--deployment-id", required=True)
    w.add_argument("--timeout", type=float, default=600.0)
    w.add_argument("--interval", type=float, default=2.0)
    w.set_defaults(func=cmd_wait)

    r = sub.add_parser("runtime", parents=[common], help="Deployment runtime summary")
    r.add_argument("--deployment-id", required=True)
    r.set_defaults(func=cmd_runtime)

    h = sub.add_parser("health-check", parents=[common], help="Runtime health check")
    h.add_argument("--deployment-id", required=True)
    h.add_argument("--service-id", required=True)
    h.set_defaults(func=cmd_health_check)

    d = sub.add_parser("destroy", parents=[common], help="Destroy deployment")
    d.add_argument("--deployment-id", required=True)
    d.set_defaults(func=cmd_destroy)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ApiHttpError as e:
        _out({"error": "api_http_error", "status": e.status, "detail": e.payload}, as_json=args.json)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
