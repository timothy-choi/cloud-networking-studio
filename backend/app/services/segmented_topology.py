"""Detect multi-segment (multi Docker bridge) topologies from persisted links."""

from __future__ import annotations

from app.models.topology import Topology


def topology_is_segmented_multinet(topology: Topology) -> bool:
    """
    Segmented mode when there are multiple distinct link ``network_name`` values.

    Single-link (or all links sharing one network name) keeps the legacy one-bridge
    ``cns-topology-<id>`` behavior for backward compatibility.
    """
    if len(topology.links) <= 1:
        return False
    names = {l.network_name for l in topology.links}
    return len(names) > 1
