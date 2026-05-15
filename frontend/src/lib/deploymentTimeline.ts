/**
 * Maps deployment event text to a stable timeline phase for operator-facing UIs (Step 32).
 * Does not change backend behavior — classification is best-effort on messages already stored.
 */

export type TimelinePhase =
  | 'deployment_created'
  | 'validation'
  | 'runtime_provisioning'
  | 'network'
  | 'containers'
  | 'traffic_test'
  | 'failure_injection'
  | 'reconcile_heal'
  | 'destroy'
  | 'other';

export interface TimelinePhaseInfo {
  phase: TimelinePhase;
  /** Short label for the timeline rail */
  label: string;
}

export function inferDeploymentTimelinePhase(message: string): TimelinePhaseInfo {
  const m = message.toLowerCase();

  if (/deployment pending|record created/.test(m)) {
    return { phase: 'deployment_created', label: 'Deployment created' };
  }
  if (/topology validation (passed|failed)/.test(m)) {
    return { phase: 'validation', label: 'Validation' };
  }
  if (/deployment deploying|invoking runtime provider|runtime provider/.test(m)) {
    return { phase: 'runtime_provisioning', label: 'Runtime provisioning' };
  }
  if (/network|cns-topology|docker network|ensured docker network|missing_network/.test(m)) {
    return { phase: 'network', label: 'Network' };
  }
  if (/container|node container|scheduled:.*->|image pull|started container|stopped container/.test(m)) {
    return { phase: 'containers', label: 'Containers' };
  }
  if (/traffic|ping|http test|icmp/.test(m)) {
    return { phase: 'traffic_test', label: 'Traffic tests' };
  }
  if (/failure|inject|kill_container|stop_container|restart_container/.test(m)) {
    return { phase: 'failure_injection', label: 'Failure injection' };
  }
  if (/reconcil|heal|healing|drift/.test(m)) {
    return { phase: 'reconcile_heal', label: 'Reconcile / heal' };
  }
  if (/destroy|teardown|stopped — runtime|deployment stopping/.test(m)) {
    return { phase: 'destroy', label: 'Destroy' };
  }

  return { phase: 'other', label: 'Event' };
}
