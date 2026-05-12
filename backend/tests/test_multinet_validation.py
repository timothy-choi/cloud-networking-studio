"""Unit tests for segmented multi-network / router validation rules."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType, Topology, TopologyLink, TopologyNode, TopologyStatus
from app.services.deployment_validation import validate_topology_for_deploy


def _base_topo() -> Topology:
    tid = uuid.uuid4()
    return Topology(
        id=tid,
        name="seg",
        description=None,
        status=TopologyStatus.DRAFT,
        runtime_target="docker",
        networking_mode="docker_bridge",
        config=None,
    )


def test_multinet_overlapping_subnets_rejected():
    topo = _base_topo()
    tid = topo.id
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    topo.nodes.append(
        TopologyNode(
            id=a,
            topology_id=tid,
            name="host",
            node_type=NodeType.HOST,
            image="alpine:latest",
            ip_address="10.1.0.10",
            config=None,
        )
    )
    topo.nodes.append(
        TopologyNode(
            id=b,
            topology_id=tid,
            name="r",
            node_type=NodeType.ROUTER,
            image="alpine:latest",
            ip_address=None,
            config=None,
        )
    )
    topo.nodes.append(
        TopologyNode(
            id=c,
            topology_id=tid,
            name="svc",
            node_type=NodeType.GENERIC,
            image="nginx:alpine",
            ip_address=None,
            config=None,
        )
    )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=a,
            target_node_id=b,
            network_name="net-a",
            cidr="10.1.0.0/24",
            gateway="10.1.0.1",
            vlan_tag=None,
            source_endpoint_ip="10.1.0.10",
            target_endpoint_ip="10.1.0.1",
            config=None,
        )
    )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=b,
            target_node_id=c,
            network_name="net-b",
            cidr="10.1.0.0/24",
            gateway="10.1.0.1",
            vlan_tag=None,
            source_endpoint_ip="10.1.0.1",
            target_endpoint_ip="10.1.0.20",
            config=None,
        )
    )
    errs = validate_topology_for_deploy(topo)
    assert any("Overlapping" in e or "Duplicate subnet" in e for e in errs)


def test_multinet_router_single_link_rejected():
    """Router must participate in ≥2 links when the topology is segmented multinet."""
    topo = _base_topo()
    tid = topo.id
    r, h, a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    topo.nodes.append(
        TopologyNode(
            id=r,
            topology_id=tid,
            name="r1",
            node_type=NodeType.ROUTER,
            image="alpine:latest",
            ip_address=None,
            config=None,
        )
    )
    topo.nodes.append(
        TopologyNode(
            id=h,
            topology_id=tid,
            name="h1",
            node_type=NodeType.HOST,
            image="alpine:latest",
            ip_address=None,
            config=None,
        )
    )
    topo.nodes.append(
        TopologyNode(
            id=a,
            topology_id=tid,
            name="peer",
            node_type=NodeType.GENERIC,
            image="alpine:latest",
            ip_address=None,
            config=None,
        )
    )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=r,
            target_node_id=h,
            network_name="net-a",
            cidr="10.1.0.0/24",
            gateway="10.1.0.1",
            source_endpoint_ip="10.1.0.1",
            target_endpoint_ip="10.1.0.10",
            config=None,
        )
    )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=h,
            target_node_id=a,
            network_name="net-b",
            cidr="10.2.0.0/24",
            gateway="10.2.0.1",
            source_endpoint_ip="10.2.0.10",
            target_endpoint_ip="10.2.0.20",
            config=None,
        )
    )
    errs = validate_topology_for_deploy(topo)
    assert any("at least two links" in e.lower() for e in errs)


def test_multinet_endpoint_outside_subnet():
    topo = _base_topo()
    tid = topo.id
    h, r, s = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    topo.nodes.append(
        TopologyNode(
            id=h,
            topology_id=tid,
            name="host-a",
            node_type=NodeType.HOST,
            image="alpine:latest",
            ip_address=None,
            config=None,
        )
    )
    topo.nodes.append(
        TopologyNode(
            id=r,
            topology_id=tid,
            name="router-1",
            node_type=NodeType.ROUTER,
            image="alpine:latest",
            ip_address=None,
            config=None,
        )
    )
    topo.nodes.append(
        TopologyNode(
            id=s,
            topology_id=tid,
            name="svc-b",
            node_type=NodeType.GENERIC,
            image="nginx:alpine",
            ip_address=None,
            config=None,
        )
    )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=h,
            target_node_id=r,
            network_name="net-a",
            cidr="10.1.0.0/24",
            gateway="10.1.0.1",
            source_endpoint_ip="10.99.0.10",
            target_endpoint_ip="10.1.0.1",
            config=None,
        )
    )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=r,
            target_node_id=s,
            network_name="net-b",
            cidr="10.2.0.0/24",
            gateway="10.2.0.1",
            source_endpoint_ip="10.2.0.1",
            target_endpoint_ip="10.2.0.20",
            config=None,
        )
    )
    errs = validate_topology_for_deploy(topo)
    assert any("outside this link's CIDR" in e for e in errs)


def test_conflicting_gateways_same_network_name():
    topo = _base_topo()
    tid = topo.id
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for nid, name, ip in (
        (a, "left", "10.1.0.10"),
        (b, "mid", "10.1.0.2"),
        (c, "right", "10.1.0.20"),
    ):
        topo.nodes.append(
            TopologyNode(
                id=nid,
                topology_id=tid,
                name=name,
                node_type=NodeType.GENERIC,
                image="alpine:latest",
                ip_address=ip,
                config=None,
            )
        )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=a,
            target_node_id=b,
            network_name="same-net",
            cidr="10.1.0.0/24",
            gateway="10.1.0.1",
            config=None,
        )
    )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=b,
            target_node_id=c,
            network_name="same-net",
            cidr="10.1.0.0/24",
            gateway="10.1.0.254",
            config=None,
        )
    )
    errs = validate_topology_for_deploy(topo)
    assert any("Conflicting gateway" in e for e in errs)


def test_gateway_not_in_cidr():
    topo = _base_topo()
    tid = topo.id
    a, b = uuid.uuid4(), uuid.uuid4()
    topo.nodes.append(
        TopologyNode(
            id=a,
            topology_id=tid,
            name="a",
            node_type=NodeType.HOST,
            image="alpine:latest",
            ip_address="10.1.0.10",
            config=None,
        )
    )
    topo.nodes.append(
        TopologyNode(
            id=b,
            topology_id=tid,
            name="b",
            node_type=NodeType.GENERIC,
            image="alpine:latest",
            ip_address="10.1.0.20",
            config=None,
        )
    )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=a,
            target_node_id=b,
            network_name="n",
            cidr="10.1.0.0/24",
            gateway="10.9.0.1",
            config=None,
        )
    )
    errs = validate_topology_for_deploy(topo)
    assert any("gateway" in e.lower() and "not within" in e.lower() for e in errs)


def test_disconnected_island_rejected():
    topo = _base_topo()
    tid = topo.id
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for nid, name in ((a, "a"), (b, "b"), (c, "c")):
        topo.nodes.append(
            TopologyNode(
                id=nid,
                topology_id=tid,
                name=name,
                node_type=NodeType.GENERIC,
                image="alpine:latest",
                ip_address="10.1.0.10" if name == "a" else ("10.1.0.20" if name == "b" else "10.1.0.30"),
                config=None,
            )
        )
    topo.links.append(
        TopologyLink(
            id=uuid.uuid4(),
            topology_id=tid,
            source_node_id=a,
            target_node_id=b,
            network_name="n",
            cidr="10.1.0.0/24",
            config=None,
        )
    )
    errs = validate_topology_for_deploy(topo)
    assert any("disconnected" in e.lower() for e in errs)
