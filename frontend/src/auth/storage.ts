/** Session keys shared by API client, auth, and dashboard project selection. */

export const CNS_ACCESS_TOKEN_KEY = 'cns_access_token';
export const CNS_SELECTED_PROJECT_KEY = 'cns_selected_project_id';

/** Remove JWT and UI-only session keys (project selector). Safe to call multiple times. */
export function clearAuthSessionStorage(): void {
  try {
    sessionStorage.removeItem(CNS_ACCESS_TOKEN_KEY);
    sessionStorage.removeItem(CNS_SELECTED_PROJECT_KEY);
  } catch {
    // ignore (private mode, etc.)
  }
}
