/** Structured deployment operation timeline (Step 53A). */

export interface TimelineEventResponse {
  id: string;
  deployment_id: string;
  event_type: string;
  status: string;
  message: string;
  request_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface DeploymentTimelineResponse {
  deployment_id: string;
  events: TimelineEventResponse[];
}
