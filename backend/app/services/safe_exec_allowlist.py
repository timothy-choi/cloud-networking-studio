"""Safe exec command allowlist (must stay aligned with ``runner/internal/runtime/safeexec``)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_FORBIDDEN = set(";&|`$><\n\r")
_DANGEROUS_SUBSTRINGS = (
    "rm ",
    " rm",
    "/rm",
    "shutdown",
    "reboot",
    "mkfs",
    " dd ",
    "/dd",
    "chmod",
    "chown",
    "apt-get",
    "apt ",
    "yum ",
    "dnf ",
    "apk ",
    "pip ",
    "npm ",
    "curl |",
    "wget |",
    "sh -",
    "bash ",
    "/bin/sh",
    "/bin/bash",
)
_PS_ARG = re.compile(r"^[a-zA-Z0-9._-]+$")
_HOST = re.compile(r"^[a-zA-Z0-9._-]+$")


def _reject(msg: str) -> tuple[list[str] | None, str]:
    return None, msg


def validate_command(raw: str) -> tuple[list[str] | None, str]:
    """Return (argv, error_message). error_message empty when allowed."""
    s = (raw or "").strip()
    if not s:
        return _reject("empty command")
    if any(ch in s for ch in _FORBIDDEN):
        return _reject("Command is not allowed in safe exec mode.")
    low = s.lower()
    for d in _DANGEROUS_SUBSTRINGS:
        if d in low:
            return _reject("Command is not allowed in safe exec mode.")
    parts = s.split()
    if not parts:
        return _reject("empty command")
    if parts[0].lower() == "rm":
        return _reject("Command is not allowed in safe exec mode.")
    cmd = parts[0]
    if cmd == "whoami":
        return (parts, "") if len(parts) == 1 else _reject("whoami takes no arguments")
    if cmd == "hostname":
        if len(parts) == 1:
            return parts, ""
        if len(parts) == 2 and parts[1] == "-f":
            return parts, ""
        return _reject("hostname: only optional -f allowed")
    if cmd == "env":
        return (parts, "") if len(parts) == 1 else _reject("env takes no arguments")
    if cmd == "ps":
        for p in parts[1:]:
            if not _PS_ARG.match(p):
                return _reject(f"ps: disallowed argument {p!r}")
        return parts, ""
    if cmd == "ip":
        if len(parts) < 2:
            return _reject("ip: need subcommand")
        if parts[1] == "addr":
            return (parts, "") if len(parts) == 2 else _reject("ip addr takes no extra args")
        if parts[1] == "route":
            if len(parts) == 2:
                return parts, ""
            if len(parts) == 3 and parts[2] == "show":
                return parts, ""
            return _reject("ip route: only optional 'show'")
        return _reject("ip: only addr or route allowed")
    if cmd == "cat":
        if len(parts) != 2 or parts[1] != "/etc/resolv.conf":
            return _reject("cat: only /etc/resolv.conf allowed")
        return parts, ""
    if cmd == "nslookup":
        if len(parts) != 2:
            return _reject("nslookup: exactly one target required")
        if not _safe_host(parts[1]):
            return _reject("nslookup: invalid target")
        return parts, ""
    if cmd in ("curl", "wget"):
        if len(parts) != 2:
            return _reject(f"{cmd}: exactly one URL required")
        err = _http_url(parts[1])
        if err:
            return None, err
        return parts, ""
    if cmd == "ping":
        if len(parts) == 2:
            if not _safe_host(parts[1]):
                return _reject("ping: invalid target")
            return ["ping", "-c", "3", parts[1]], ""
        if len(parts) == 4 and parts[1] == "-c":
            try:
                n = int(parts[2])
            except ValueError:
                return _reject("ping: count must be 1-10")
            if n < 1 or n > 10:
                return _reject("ping: count must be 1-10")
            if not _safe_host(parts[3]):
                return _reject("ping: invalid target")
            return parts, ""
        return _reject("ping: use 'ping <host>' or 'ping -c N <host>' (N 1-10)")
    return _reject("Command is not allowed in safe exec mode.")


def _safe_host(s: str) -> bool:
    return 0 < len(s) <= 253 and bool(_HOST.match(s))


def _http_url(s: str) -> str:
    u = urlparse(s)
    if u.scheme not in ("http", "https") or not u.netloc:
        return "curl/wget: URL must be http(s) with host"
    if any(x in s for x in (" ", "\t")):
        return "curl/wget: URL must be a single token"
    return ""
