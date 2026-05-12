"""Pre-deploy topology checks — invalid graphs return structured error strings."""

from __future__ import annotations

import ipaddress
from collections import Counter, defaultdict
from typing import Iterable

from app.models.topology import NodeType, Topology, TopologyLink
from app.services.segmented_topology import topology_is_segmented_multinet


def _graph_is_fully_connected(node_ids: set, links: Iterable[TopologyLink]) -> bool:
    """Undirected connectivity: every node must appear in one component."""
    if len(node_ids) <= 1:
        return True
    adj: dict[object, set] = defaultdict(set)
    for link in links:
        u, v = link.source_node_id, link.target_node_id
        if u in node_ids and v in node_ids:
            adj[u].add(v)
            adj[v].add(u)
    start = next(iter(node_ids))
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for nb in adj.get(cur, ()):
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen == node_ids


def _validate_multinet_extra(topology: Topology) -> list[str]:
    errs: list[str] = []
    node_by_id = {n.id: n for n in topology.nodes}
    degrees: dict = {}
    for link in topology.links:
        degrees[link.source_node_id] = degrees.get(link.source_node_id, 0) + 1
        degrees[link.target_node_id] = degrees.get(link.target_node_id, 0) + 1

    parsed: list[tuple[object, ipaddress.IPv4Network | ipaddress.IPv6Network]] = []
    for link in topology.links:
        raw = (link.cidr or "").strip()
        if not raw:
            errs.append(
                f"Segmented multi-network mode: link {link.network_name!r} (id={link.id}) must declare a CIDR."
            )
            continue
        try:
            parsed.append((link.id, ipaddress.ip_network(raw, strict=False)))
        except ValueError:
            errs.append(f"Link id={link.id} has invalid CIDR {raw!r}.")

    for i, (id_a, na) in enumerate(parsed):
        for id_b, nb in parsed[i + 1 :]:
            if na.overlaps(nb):
                if na == nb:
                    errs.append(
                        f"Duplicate subnet {na} on multiple links (link ids {id_a}, {id_b})."
                    )
                else:
                    errs.append(
                        f"Overlapping link subnets: {na} and {nb} (link ids {id_a}, {id_b})."
                    )

    for nid, deg in degrees.items():
        node = node_by_id.get(nid)
        if node is None:
            continue
        if node.node_type == NodeType.ROUTER and deg < 2:
            errs.append(
                f"Router node {node.name!r} must participate in at least two links "
                "in segmented multi-network mode."
            )

    for link in topology.links:
        src = node_by_id.get(link.source_node_id)
        tgt = node_by_id.get(link.target_node_id)
        if src is None or tgt is None:
            continue
        s_ip = (link.source_endpoint_ip or "").strip() or (src.ip_address or "").strip()
        t_ip = (link.target_endpoint_ip or "").strip() or (tgt.ip_address or "").strip()
        if src.node_type == NodeType.ROUTER and degrees.get(src.id, 0) > 1:
            if not (link.source_endpoint_ip or "").strip():
                errs.append(
                    f"Link id={link.id}: set source_endpoint_ip for router {src.name!r} "
                    "on this segment (multinet)."
                )
        if tgt.node_type == NodeType.ROUTER and degrees.get(tgt.id, 0) > 1:
            if not (link.target_endpoint_ip or "").strip():
                errs.append(
                    f"Link id={link.id}: set target_endpoint_ip for router {tgt.name!r} "
                    "on this segment (multinet)."
                )
        if not s_ip or not t_ip:
            errs.append(
                f"Link id={link.id} ({link.network_name!r}) is missing a resolved IPv4 "
                "on one endpoint (set per-link endpoint IPs or node ip_address)."
            )
            continue

        raw_cidr = (link.cidr or "").strip()
        if not raw_cidr:
            continue
        try:
            seg_net = ipaddress.ip_network(raw_cidr, strict=False)
        except ValueError:
            continue
        for label, ip_s in (("source", s_ip), ("target", t_ip)):
            try:
                addr = ipaddress.ip_address(ip_s)
            except ValueError:
                errs.append(f"Link id={link.id}: invalid {label} IP {ip_s!r}.")
                continue
            if addr not in seg_net:
                errs.append(
                    f"Link id={link.id}: {label} IP {ip_s} is outside this link's CIDR {seg_net}."
                )
            elif isinstance(seg_net, ipaddress.IPv4Network) and seg_net.num_addresses > 2:
                if addr in (seg_net.network_address, seg_net.broadcast_address):
                    errs.append(
                        f"Link id={link.id}: {label} IP {ip_s} must not be the network or "
                        f"broadcast address of {seg_net}."
                    )

    return errs


def validate_topology_for_deploy(topology: Topology) -> list[str]:
    """
    Return a list of human-readable validation errors (empty if OK).

    Rules:
    - At least one node.
    - Multi-node topologies need at least one link.
    - No duplicate non-empty intended node IPs.
    - Every link endpoint must reference an existing node.
    - If any link declares a parseable CIDR, every node static IP must fall in at least one of those networks.
    - Segmented multi-network: non-overlapping subnets, per-link CIDR, router link rules, endpoint IPs in subnet.
    - Explicit gateways must lie in their link CIDR; conflicting gateways on the same logical network name are rejected.
    - Multi-node graphs must be simply connected via links (no isolated islands).
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

    gw_by_network: dict[str, list[str]] = defaultdict(list)
    for link in topology.links:
        g = (link.gateway or "").strip()
        if g:
            gw_by_network[link.network_name].append(g)
    for net, gws in gw_by_network.items():
        uniq = {x for x in gws}
        if len(uniq) > 1:
            errors.append(
                f"Conflicting gateway IPv4 values on logical network {net!r}: "
                f"{', '.join(sorted(uniq))}."
            )

    for link in topology.links:
        raw_cidr = (link.cidr or "").strip()
        gw_s = (link.gateway or "").strip()
        if not raw_cidr or not gw_s:
            continue
        try:
            net = ipaddress.ip_network(raw_cidr, strict=False)
            gw = ipaddress.ip_address(gw_s)
        except ValueError:
            continue
        if gw not in net:
            errors.append(
                f"Link id={link.id}: gateway {gw_s} is not within CIDR {raw_cidr}."
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

    if parsed_nets and not topology_is_segmented_multinet(topology):
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

    if topology_is_segmented_multinet(topology):
        errors.extend(_validate_multinet_extra(topology))

    if len(nodes) > 1 and topology.links and not _graph_is_fully_connected(node_ids, topology.links):
        errors.append(
            "Topology graph is disconnected: every node must be reachable through links "
            "(no isolated islands)."
        )

    return errors
