import { getApiBase, getStoredAccessToken, ApiError } from './client';

export type TopologyIacExportKind =
  | 'docker-compose'
  | 'kubernetes'
  | 'terraform'
  | 'ansible'
  | 'archive';

export const IAC_EXPORT_OPTIONS: {
  kind: TopologyIacExportKind;
  label: string;
  filename: string;
  description: string;
}[] = [
  {
    kind: 'docker-compose',
    label: 'Docker Compose',
    filename: 'docker-compose.cns.yml',
    description: 'Compose services, networks, ports, env, and commands from node config.',
  },
  {
    kind: 'kubernetes',
    label: 'Kubernetes YAML',
    filename: 'kubernetes.cns.yaml',
    description: 'Namespace, Deployments, and Services skeleton from topology nodes.',
  },
  {
    kind: 'terraform',
    label: 'Terraform skeleton',
    filename: 'terraform-cns.zip',
    description: 'main.tf, variables.tf, outputs.tf, and README with TODOs.',
  },
  {
    kind: 'ansible',
    label: 'Ansible skeleton',
    filename: 'ansible-cns.zip',
    description: 'inventory.ini, playbook.yml, and README with TODO tasks.',
  },
  {
    kind: 'archive',
    label: 'Download all',
    filename: 'cns-iac-export.zip',
    description: 'Zip containing Compose, Kubernetes, Terraform, and Ansible artifacts.',
  },
];

export function topologyIacExportUrl(topologyId: string, kind: TopologyIacExportKind) {
  return `${getApiBase()}/topologies/${topologyId}/exports/${kind}`;
}

export async function downloadTopologyIacExport(topologyId: string, kind: TopologyIacExportKind) {
  const token = getStoredAccessToken();
  const res = await fetch(topologyIacExportUrl(topologyId, kind), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    let detail: unknown = await res.text();
    try {
      detail = JSON.parse(String(detail));
    } catch {
      /* plain text */
    }
    throw new ApiError(res.status, res.statusText, detail);
  }
  const blob = await res.blob();
  const opt = IAC_EXPORT_OPTIONS.find((o) => o.kind === kind);
  const filename = opt?.filename ?? 'cns-export.bin';
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
}
