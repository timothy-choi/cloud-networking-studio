import { apiFetch } from './client';

export type OnboardingStepState = {
  id: string;
  title: string;
  description: string;
  completed: boolean;
  auto_detected: boolean;
};

export type OnboardingStatusPayload = {
  has_seen_onboarding: boolean;
  completed_steps: string[];
  steps: OnboardingStepState[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type StartDemoResponse = {
  project_id: string;
  topology_id: string;
  deployment_id: string;
  resumed: boolean;
  detail?: string | null;
};

export async function getOnboardingStatus(): Promise<OnboardingStatusPayload> {
  return apiFetch<OnboardingStatusPayload>('/onboarding/status');
}

export async function updateOnboardingStatus(body: {
  has_seen_onboarding?: boolean;
  completed_steps?: string[];
}): Promise<OnboardingStatusPayload> {
  return apiFetch<OnboardingStatusPayload>('/onboarding/status', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function completeOnboardingStep(step: string): Promise<OnboardingStatusPayload> {
  return apiFetch<OnboardingStatusPayload>('/onboarding/complete-step', {
    method: 'POST',
    body: JSON.stringify({ step }),
  });
}

export async function resetOnboarding(): Promise<OnboardingStatusPayload> {
  return apiFetch<OnboardingStatusPayload>('/onboarding/reset', {
    method: 'POST',
  });
}

export async function startDemoLab(): Promise<StartDemoResponse> {
  return apiFetch<StartDemoResponse>('/onboarding/start-demo', {
    method: 'POST',
  });
}
