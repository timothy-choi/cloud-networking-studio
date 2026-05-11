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
      const client = await topoApi.createNode(topologyId, {
        name: `client-${r}`,
        node_type: 'host',
        image: 'alpine:latest',
        ip_address: `10.110.${Math.floor(Math.random() * 200)}.10`,
        config: editorPos(100, 160),
      });
      const server = await topoApi.createNode(topologyId, {
        name: `server-${r}`,
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: `10.110.${Math.floor(Math.random() * 200)}.20`,
        config: editorPos(440, 160),
      });
      await topoApi.createLink(topologyId, {
        source_node_id: client.id,
        target_node_id: server.id,
        network_name: `cs-${r}`,
        cidr: `10.110.${Math.floor(Math.random() * 200)}.0/24`,
        config: null,
      });
      return;
    }

    case 'web-tier': {
      const lb = await topoApi.createNode(topologyId, {
        name: `lb-${r}`,
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: null,
        config: editorPos(260, 70),
      });
      const webA = await topoApi.createNode(topologyId, {
        name: `web-a-${r}`,
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: null,
        config: editorPos(120, 230),
      });
      const webB = await topoApi.createNode(topologyId, {
        name: `web-b-${r}`,
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: null,
        config: editorPos(400, 230),
      });
      const db = await topoApi.createNode(topologyId, {
        name: `db-${r}`,
        node_type: 'generic',
        image: 'postgres:16-alpine',
        ip_address: null,
        config: editorPos(260, 400),
      });
      const o = Math.floor(Math.random() * 160) + 40;
      await topoApi.createLink(topologyId, {
        source_node_id: lb.id,
        target_node_id: webA.id,
        network_name: `fe-${r}-a`,
        cidr: `10.${o}.1.0/24`,
        config: null,
      });
      await topoApi.createLink(topologyId, {
        source_node_id: lb.id,
        target_node_id: webB.id,
        network_name: `fe-${r}-b`,
        cidr: `10.${o}.2.0/24`,
        config: null,
      });
      await topoApi.createLink(topologyId, {
        source_node_id: webA.id,
        target_node_id: db.id,
        network_name: `data-${r}-a`,
        cidr: `10.${o}.10.0/24`,
        config: null,
      });
      await topoApi.createLink(topologyId, {
        source_node_id: webB.id,
        target_node_id: db.id,
        network_name: `data-${r}-b`,
        cidr: `10.${o}.11.0/24`,
        config: null,
      });
      return;
    }

    case 'load-balancer': {
      const lb = await topoApi.createNode(topologyId, {
        name: `lb-${r}`,
        node_type: 'generic',
        image: 'nginx:alpine',
        ip_address: null,
        config: editorPos(280, 80),
      });
      const apps: { id: string }[] = [];
      for (let i = 0; i < 3; i += 1) {
        const n = await topoApi.createNode(topologyId, {
          name: `app-${i + 1}-${r}`,
          node_type: 'generic',
          image: 'nginx:alpine',
          ip_address: null,
          config: editorPos(80 + i * 220, 280),
        });
        apps.push(n);
      }
      const base = Math.floor(Math.random() * 200) + 30;
      for (let i = 0; i < apps.length; i += 1) {
        await topoApi.createLink(topologyId, {
          source_node_id: lb.id,
          target_node_id: apps[i].id,
          network_name: `vip-${r}-${i}`,
          cidr: `10.${base}.${i}.0/24`,
          config: null,
        });
      }
      return;
    }

    case 'router-switch': {
      const router = await topoApi.createNode(topologyId, {
        name: `router-${r}`,
        node_type: 'router',
        image: 'alpine:latest',
        ip_address: null,
        config: editorPos(160, 180),
      });
      const sw = await topoApi.createNode(topologyId, {
        name: `switch-${r}`,
        node_type: 'switch',
        image: 'alpine:latest',
        ip_address: null,
        config: editorPos(460, 180),
      });
      await topoApi.createLink(topologyId, {
        source_node_id: router.id,
        target_node_id: sw.id,
        network_name: `rs-${r}`,
        cidr: `10.120.${Math.floor(Math.random() * 200)}.0/24`,
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
          name: `mesh-${i}-${r}`,
          node_type: 'host',
          image: 'alpine:latest',
          ip_address: null,
          config: editorPos(coords[i][0], coords[i][1]),
        });
        ids.push(n.id);
      }
      let k = 0;
      const baseOct = Math.floor(Math.random() * 200) + 20;
      for (let i = 0; i < ids.length; i += 1) {
        for (let j = i + 1; j < ids.length; j += 1) {
          k += 1;
          await topoApi.createLink(topologyId, {
            source_node_id: ids[i],
            target_node_id: ids[j],
            network_name: `mesh-${r}-${k}`,
            cidr: `10.${baseOct}.${k}.0/24`,
            config: null,
          });
        }
      }
      return;
    }
  }
}
