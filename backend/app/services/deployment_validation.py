"""Pre-deploy topology checks — invalid graphs return structured error strings."""

from __future__ import annotations

import ipaddress
from collections import Counter

from app.models.topology import Topology


def validate_topology_for_deploy(topology: Topology) -> list[str]:
    """
    Return a list of human-readable validation errors (empty if OK).

    Rules:
    - At least one node.
    - Multi-node topologies need at least one link.
    - No duplicate non-empty intended node IPs.
    - Every link endpoint must reference an existing node.
    - If any link declares a parseable CIDR, every node static IP must fall in at least one of those networks.
    """
    errors: list[str] = []
    nodes = list(topology.nodes)
    node_ids = {n.id for n in nodes}

    if len(nodes) < 1:
        errors.append("Topology must have at least one node before deploy.")

    if len(nodes) > 1 and len(topology.links) < 1:
        errors.append("Multi-node topology requires at least one link before deploy.")

    stripped_ips = [(n.id, (n.ip_address or "").strip()) for n in nodes]
    nonempty = [ip for _, ip in stripped_ips if ip]
    for ip, count in Counter(nonempty).items():
        if count > 1:
            errors.append(f"Duplicate intended node IP address: {ip}")

    for link in topology.links:
        if link.source_node_id not in node_ids:
            errors.append(
                f"Link references missing source node (link id={link.id}, "
                f"source_node_id={link.source_node_id})."
            )
        if link.target_node_id not in node_ids:
            errors.append(
                f"Link references missing target node (link id={link.id}, "
                f"target_node_id={link.target_node_id})."
            )

    parsed_nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for link in topology.links:
        raw = (link.cidr or "").strip()
        if not raw:
            continue
        try:
            parsed_nets.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            errors.append(f"Link id={link.id} has invalid CIDR {raw!r}.")

    if parsed_nets:
        for n in nodes:
            ip_s = (n.ip_address or "").strip()
            if not ip_s:
                continue
            try:
                addr = ipaddress.ip_address(ip_s)
            except ValueError:
                errors.append(f"Node {n.name!r} has invalid IP address {ip_s!r}.")
                continue
            if not any(addr in net for net in parsed_nets):
                nets_s = ", ".join(str(net) for net in parsed_nets)
                errors.append(
                    f"Node {n.name!r} IP {ip_s} is not within any link subnet ({nets_s})."
                )

    return errors
