import type { FlowWorkloadStatus } from '../lib/flowTopology';

export type { Edge, Node } from '@xyflow/react';
export type { CnsFlowNodeData } from '../lib/flowTopology';

/** Live controller hints layered onto canvas nodes when runtime data exists. */
export interface RuntimeNodeOverlay {
  workload: FlowWorkloadStatus;
  runtimeIp: string | null;
  degraded: boolean;
}
