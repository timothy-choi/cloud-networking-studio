import { apiFetchBlob, apiFetch, resolveApiUrl } from './client';

export type TopologyIacExportKind =
  | 'docker-compose'
  | 'kubernetes'
  | 'terraform'
  | 'ansible'
  | 'archive';

export type IaCExportOption = {
  kind: TopologyIacExportKind;
  label: string;
  filename: string;
  description: string;
};

/** Blueprint exports runnable outside CNS (Compose / Kubernetes). */
export const IAC_RUNTIME_EXPORTS: IaCExportOption[] = [
  {
    kind: 'docker-compose',
    label: 'Download Docker Compose',
    filename: 'docker-compose.cns.yml',
    description: 'Compose services, networks, ports, env, and commands from node config.',
  },
  {
    kind: 'kubernetes',
    label: 'Download Kubernetes YAML',
    filename: 'kubernetes.cns.yaml',
    description: 'Namespace, Deployments, and Services skeleton from topology nodes.',
  },
];

/** Skeleton archives with TODOs — run Terraform/Ansible outside CNS. */
export const IAC_SKELETON_EXPORTS: IaCExportOption[] = [
  {
    kind: 'terraform',
    label: 'Download Terraform skeleton',
    filename: 'terraform-cns.zip',
    description: 'main.tf, variables.tf, outputs.tf, and README with TODOs.',
  },
  {
    kind: 'ansible',
    label: 'Download Ansible skeleton',
    filename: 'ansible-cns.zip',
    description: 'inventory.ini, playbook.yml, and README with TODO tasks.',
  },
];

export const IAC_ARCHIVE_EXPORT: IaCExportOption = {
  kind: 'archive',
  label: 'Download all',
  filename: 'cns-iac-export.zip',
  description: 'Zip containing Compose, Kubernetes, Terraform, and Ansible artifacts.',
};

export const IAC_EXPORT_OPTIONS: IaCExportOption[] = [
  ...IAC_RUNTIME_EXPORTS,
  ...IAC_SKELETON_EXPORTS,
  IAC_ARCHIVE_EXPORT,
];

export function topologyIacExportUrl(topologyId: string, kind: TopologyIacExportKind) {
  return resolveApiUrl(`/topologies/${topologyId}/exports/${kind}`);
}

export async function downloadTopologyIacExport(topologyId: string, kind: TopologyIacExportKind) {
  const blob = await apiFetchBlob(`/topologies/${topologyId}/exports/${kind}`);
  const opt = IAC_EXPORT_OPTIONS.find((o) => o.kind === kind);
  const filename = opt?.filename ?? 'cns-export.bin';
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
}

export type IaCExportWarning = {
  severity: string;
  code: string;
  message: string;
  node_name?: string | null;
};

export type IaCExportArtifact = {
  id: string;
  name: string;
  type: string;
  category: string;
  download_path: string;
};

export type TopologyIacExportPreview = {
  topology_id: string;
  topology_name: string;
  runtime_target: string;
  networking_mode: string;
  artifacts: IaCExportArtifact[];
  previews: Record<string, string>;
  terraform_files: string[];
  ansible_files: string[];
  archive_files: string[];
  warnings: IaCExportWarning[];
  unsupported_features: string[];
  todo_notes: string[];
  metadata?: Record<string, unknown>;
};

export type PreviewArtifactId = 'docker-compose' | 'kubernetes' | 'terraform' | 'ansible' | 'archive';

export function fetchTopologyIacExportPreview(topologyId: string) {
  return apiFetch<TopologyIacExportPreview>(`/topologies/${topologyId}/exports/preview`);
}
