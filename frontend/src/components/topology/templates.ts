import * as topoApi from '../../api/topologies';
import type { TopologyTemplateId } from '../../types/templates';
import { EDITOR_POSITION_KEY } from '../../types/topology';

function randSuffix(): string {
  return Math.random().toString(36).slice(2, 6);
}

function editorPos(x: number, y: number): Record<string, unknown> {
  return { [EDITOR_POSITION_KEY]: { x, y } };
}

/**
 * Appends template nodes and links to an existing topology (does not clear it).
 */
export async function applyTopologyTemplate(
  topologyId: string,
  template: TopologyTemplateId,
): Promise<void> {
  const r = randSuffix();

  switch (template) {
    case 'client-server': {
      const o = 50;
      const cidr = `10.${o}.0.0/24`;
      const client = await topoApi.createNode(topologyId, {
        name: 'cli-edge',
        node_type: 'host',
        image: 'alpine:latest',
        ip_address: `10.${o}.0.10`,
        config: editorPos(120, 200),
      });
      const server = await topoApi.createNode(topologyId, {
        name: 'svc-origin',
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: `10.${o}.0.20`,
        config: editorPos(520, 200),
      });
      await topoApi.createLink(topologyId, {
        source_node_id: client.id,
        target_node_id: server.id,
        network_name: `cs-east-${r}`,
        cidr,
        config: null,
      });
      return;
    }

    case 'web-tier': {
      const lb = await topoApi.createNode(topologyId, {
        name: 'ingress-lb',
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: '10.60.0.5',
        config: editorPos(280, 80),
      });
      const webA = await topoApi.createNode(topologyId, {
        name: 'web-tier-a',
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: '10.60.1.10',
        config: editorPos(120, 240),
      });
      const webB = await topoApi.createNode(topologyId, {
        name: 'web-tier-b',
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: '10.60.1.11',
        config: editorPos(440, 240),
      });
      const db = await topoApi.createNode(topologyId, {
        name: 'data-tier',
        node_type: 'generic',
        image: 'postgres:16-alpine',
        ip_address: '10.60.2.10',
        config: editorPos(280, 420),
      });
      const o = 60;
      await topoApi.createLink(topologyId, {
        source_node_id: lb.id,
        target_node_id: webA.id,
        network_name: `fe-${r}-a`,
        cidr: `10.${o}.10.0/24`,
        config: null,
      });
      await topoApi.createLink(topologyId, {
        source_node_id: lb.id,
        target_node_id: webB.id,
        network_name: `fe-${r}-b`,
        cidr: `10.${o}.11.0/24`,
        config: null,
      });
      await topoApi.createLink(topologyId, {
        source_node_id: webA.id,
        target_node_id: db.id,
        network_name: `data-${r}-a`,
        cidr: `10.${o}.20.0/24`,
        config: null,
      });
      await topoApi.createLink(topologyId, {
        source_node_id: webB.id,
        target_node_id: db.id,
        network_name: `data-${r}-b`,
        cidr: `10.${o}.21.0/24`,
        config: null,
      });
      return;
    }

    case 'load-balancer': {
      const lb = await topoApi.createNode(topologyId, {
        name: 'vip-lb',
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: '10.70.0.2',
        config: editorPos(300, 100),
      });
      const apps: { id: string }[] = [];
      const labels = ['svc-a', 'svc-b'];
      for (let i = 0; i < 2; i += 1) {
        const n = await topoApi.createNode(topologyId, {
          name: labels[i],
          node_type: 'generic',
          image: 'nginx:alpine',
          ip_address: `10.70.${i + 1}.10`,
          config: editorPos(120 + i * 360, 320),
        });
        apps.push(n);
      }
      const base = 70;
      for (let i = 0; i < apps.length; i += 1) {
        await topoApi.createLink(topologyId, {
          source_node_id: lb.id,
          target_node_id: apps[i].id,
          network_name: `vip-${r}-${i}`,
          cidr: `10.${base}.${10 + i}.0/24`,
          config: null,
        });
      }
      return;
    }

    case 'router-switch': {
      const router = await topoApi.createNode(topologyId, {
        name: 'edge-router',
        node_type: 'router',
        image: 'alpine:latest',
        ip_address: '10.80.0.1',
        config: editorPos(160, 200),
      });
      const sw = await topoApi.createNode(topologyId, {
        name: 'fabric-sw',
        node_type: 'switch',
        image: 'alpine:latest',
        ip_address: '10.80.0.2',
        config: editorPos(500, 200),
      });
      await topoApi.createLink(topologyId, {
        source_node_id: router.id,
        target_node_id: sw.id,
        network_name: `lab-fabric-${r}`,
        cidr: '10.80.100.0/24',
        config: null,
      });
      return;
    }

    case 'mesh': {
      const ids: string[] = [];
      const coords = [
        [140, 140],
        [380, 140],
        [140, 340],
        [380, 340],
      ] as const;
      for (let i = 0; i < 4; i += 1) {
        const n = await topoApi.createNode(topologyId, {
          name: `mesh-svc-${i + 1}`,
          node_type: 'host',
          image: 'alpine:latest',
          ip_address: `10.90.${i + 1}.10`,
          config: editorPos(coords[i][0], coords[i][1]),
        });
        ids.push(n.id);
      }
      let k = 0;
      const baseOct = 90;
      for (let i = 0; i < ids.length; i += 1) {
        for (let j = i + 1; j < ids.length; j += 1) {
          k += 1;
          await topoApi.createLink(topologyId, {
            source_node_id: ids[i],
            target_node_id: ids[j],
            network_name: `mesh-${r}-${k}`,
            cidr: `10.${baseOct}.${40 + k}.0/24`,
            config: null,
          });
        }
      }
      return;
    }

    case 'routed-host-router-service': {
      const host = await topoApi.createNode(topologyId, {
        name: 'host-a',
        node_type: 'host',
        image: 'alpine:latest',
        ip_address: '10.72.0.10',
        config: editorPos(100, 240),
      });
      const router = await topoApi.createNode(topologyId, {
        name: 'router-1',
        node_type: 'router',
        image: 'alpine:latest',
        ip_address: null,
        config: editorPos(420, 240),
      });
      const service = await topoApi.createNode(topologyId, {
        name: 'service-b',
        node_type: 'generic',
        image: 'busybox:1.36',
        ip_address: '10.73.0.20',
        config: editorPos(720, 240),
      });
      await topoApi.createLink(topologyId, {
        source_node_id: host.id,
        target_node_id: router.id,
        network_name: 'net-a',
        cidr: '10.72.0.0/24',
        gateway: '10.72.0.1',
        source_endpoint_ip: '10.72.0.10',
        target_endpoint_ip: '10.72.0.1',
        config: null,
      });
      await topoApi.createLink(topologyId, {
        source_node_id: router.id,
        target_node_id: service.id,
        network_name: 'net-b',
        cidr: '10.73.0.0/24',
        gateway: '10.73.0.1',
        source_endpoint_ip: '10.73.0.1',
        target_endpoint_ip: '10.73.0.20',
        config: null,
      });
      return;
    }
  }
}

/** Replace all nodes/links with the standard demo lab (matches backend demo script intent). */
export async function resetTopologyToDemoLab(topologyId: string): Promise<void> {
  const links = await topoApi.listLinks(topologyId);
  const nodes = await topoApi.listNodes(topologyId);
  for (const l of links) {
    await topoApi.deleteLink(topologyId, l.id);
  }
  for (const n of nodes) {
    await topoApi.deleteNode(topologyId, n.id);
  }
  const thirdOctet = 80 + Math.floor(Math.random() * 120);
  const cidr = `10.${thirdOctet}.0.0/24`;
  const hostIp = `10.${thirdOctet}.0.10`;
  const svcIp = `10.${thirdOctet}.0.20`;
  const host = await topoApi.createNode(topologyId, {
    name: 'host-a',
    node_type: 'host',
    image: 'alpine:latest',
    ip_address: hostIp,
    config: editorPos(160, 220),
  });
  const svc = await topoApi.createNode(topologyId, {
    name: 'service-b',
    node_type: 'generic',
    image: 'nginx:alpine',
    ip_address: svcIp,
    config: editorPos(520, 220),
  });
  await topoApi.createLink(topologyId, {
    source_node_id: host.id,
    target_node_id: svc.id,
    network_name: `demo-net-${thirdOctet}`,
    cidr,
    config: null,
  });
}
