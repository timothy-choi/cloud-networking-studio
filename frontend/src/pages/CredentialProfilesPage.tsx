import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatApiError } from '../api/client';
import {
  createCredentialProfile,
  CREDENTIAL_TYPE_BY_PROVIDER,
  deleteCredentialProfile,
  listCredentialProfiles,
  secretPlaceholder,
  updateCredentialProfile,
  validateCredentialProfile,
  type CredentialProfile,
  type CredentialProvider,
} from '../api/credentialProfiles';
import { listProjects, type ProjectResponse } from '../api/projects';
import { CNS_SELECTED_PROJECT_KEY } from '../auth/storage';
import { SectionEmptyState } from '../components/SectionEmptyState';
import { Spinner } from '../components/Spinner';

function readSessionProjectId(): string | null {
  try {
    return sessionStorage.getItem(CNS_SELECTED_PROJECT_KEY);
  } catch {
    return null;
  }
}

function fmtWhen(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, { hour12: false });
  } catch {
    return iso;
  }
}

function validationTone(status: string): string {
  if (status === 'valid') return 'text-emerald-700 dark:text-emerald-400';
  if (status === 'invalid') return 'text-red-700 dark:text-red-400';
  return 'text-amber-700 dark:text-amber-400';
}

type FormMode = 'create' | 'edit' | null;

const PROVIDERS: { id: CredentialProvider; label: string }[] = [
  { id: 'gcp', label: 'Google Cloud (GCP)' },
  { id: 'aws', label: 'Amazon Web Services (AWS)' },
  { id: 'azure', label: 'Microsoft Azure' },
];

export function CredentialProfilesPage() {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [projectId, setProjectId] = useState<string | null>(readSessionProjectId());
  const [profiles, setProfiles] = useState<CredentialProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [formMode, setFormMode] = useState<FormMode>(null);
  const [editing, setEditing] = useState<CredentialProfile | null>(null);
  const [name, setName] = useState('');
  const [provider, setProvider] = useState<CredentialProvider>('gcp');
  const [secret, setSecret] = useState('');

  const loadProjects = useCallback(async () => {
    const rows = await listProjects();
    setProjects(rows);
    if (!projectId && rows.length > 0) {
      setProjectId(rows[0].id);
    }
  }, [projectId]);

  const loadProfiles = useCallback(async () => {
    if (!projectId) {
      setProfiles([]);
      return;
    }
    setLoading(true);
    setErr(null);
    try {
      setProfiles(await listCredentialProfiles(projectId));
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadProjects().catch((e) => setErr(formatApiError(e)));
  }, [loadProjects]);

  useEffect(() => {
    void loadProfiles();
  }, [loadProfiles]);

  const selectedProject = useMemo(
    () => projects.find((p) => p.id === projectId) ?? null,
    [projects, projectId],
  );

  function openCreate() {
    setFormMode('create');
    setEditing(null);
    setName('');
    setProvider('gcp');
    setSecret('');
    setErr(null);
  }

  function openEdit(profile: CredentialProfile) {
    setFormMode('edit');
    setEditing(profile);
    setName(profile.name);
    setProvider(profile.provider);
    setSecret('');
    setErr(null);
  }

  function closeForm() {
    setFormMode(null);
    setEditing(null);
    setSecret('');
  }

  async function onSubmitForm(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId) return;
    const trimmedName = name.trim();
    if (!trimmedName) return;
    setBusy(true);
    setErr(null);
    try {
      if (formMode === 'create') {
        const trimmedSecret = secret.trim();
        if (!trimmedSecret) {
          setErr('Secret JSON is required.');
          return;
        }
        await createCredentialProfile(projectId, {
          name: trimmedName,
          provider,
          credential_type: CREDENTIAL_TYPE_BY_PROVIDER[provider],
          secret: trimmedSecret,
        });
      } else if (formMode === 'edit' && editing) {
        await updateCredentialProfile(editing.id, {
          name: trimmedName,
          ...(secret.trim() ? { secret: secret.trim() } : {}),
        });
      }
      closeForm();
      await loadProfiles();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(profile: CredentialProfile) {
    if (
      !window.confirm(
        `Delete credential profile "${profile.name}"? Deployments referencing it will fail until updated.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await deleteCredentialProfile(profile.id);
      await loadProfiles();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function onValidate(profile: CredentialProfile) {
    setBusy(true);
    setErr(null);
    try {
      await validateCredentialProfile(profile.id);
      await loadProfiles();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/dashboard" className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Credential profiles
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-cns-muted">
          Store encrypted cloud credentials per project. Use{' '}
          <code className="font-mono text-xs">credential:&lt;profile_id&gt;</code> in infrastructure deployments.
          Secrets are encrypted at rest and never returned by the API.
        </p>
      </div>

      {err ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {err}
        </div>
      ) : null}

      <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <label className="text-xs text-cns-label">
            Project
            <select
              value={projectId ?? ''}
              onChange={(e) => setProjectId(e.target.value || null)}
              className="mt-1 block min-w-[14rem] rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            >
              {projects.length === 0 ? <option value="">No projects</option> : null}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={!projectId || busy}
            onClick={openCreate}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Create profile
          </button>
        </div>
        {selectedProject ? (
          <p className="mt-2 text-xs text-cns-muted">
            Profiles are scoped to <span className="font-medium">{selectedProject.name}</span>.
          </p>
        ) : null}
      </section>

      {formMode ? (
        <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/80">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
            {formMode === 'create' ? 'Create credential profile' : 'Edit credential profile'}
          </h2>
          <form onSubmit={(e) => void onSubmitForm(e)} className="mt-3 space-y-3">
            <label className="block text-xs text-cns-label">
              Name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full max-w-md rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                required
              />
            </label>
            {formMode === 'create' ? (
              <label className="block text-xs text-cns-label">
                Provider
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value as CredentialProvider)}
                  className="mt-1 w-full max-w-md rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                >
                  {PROVIDERS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : editing ? (
              <p className="text-xs text-cns-muted">
                Provider: <span className="font-medium">{editing.provider}</span> · type{' '}
                <code className="font-mono">{editing.credential_type}</code>
              </p>
            ) : null}
            <label className="block text-xs text-cns-label">
              {formMode === 'edit' ? 'New secret JSON (leave blank to keep current)' : 'Secret JSON'}
              <textarea
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                rows={6}
                placeholder={secretPlaceholder(formMode === 'edit' && editing ? editing.provider : provider)}
                className="mt-1 w-full max-w-2xl rounded border px-2 py-1.5 font-mono text-xs dark:border-zinc-600 dark:bg-zinc-900"
                required={formMode === 'create'}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={busy}
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? 'Saving…' : formMode === 'create' ? 'Create' : 'Save changes'}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={closeForm}
                className="rounded-lg border border-zinc-300 px-4 py-2 text-sm dark:border-zinc-600"
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
        {loading ? (
          <div className="flex items-center gap-2 p-4 text-sm text-cns-muted">
            <Spinner /> Loading profiles…
          </div>
        ) : profiles.length === 0 ? (
          <SectionEmptyState
            title="No credential profiles"
            description="Create a profile to deploy infrastructure into your own cloud account."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase text-cns-label dark:border-zinc-700">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Provider</th>
                  <th className="px-4 py-3 font-medium">Validation</th>
                  <th className="px-4 py-3 font-medium">Reference</th>
                  <th className="px-4 py-3 font-medium">Last used</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((profile) => (
                  <tr key={profile.id} className="border-b border-zinc-100 dark:border-zinc-800">
                    <td className="px-4 py-3 font-medium">{profile.name}</td>
                    <td className="px-4 py-3">{profile.provider}</td>
                    <td className="px-4 py-3">
                      <span className={validationTone(profile.validation_status)}>
                        {profile.validation_status}
                      </span>
                      {profile.validation_message ? (
                        <p className="mt-0.5 max-w-xs text-xs text-cns-muted">{profile.validation_message}</p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <code className="font-mono text-[11px]">{profile.credentials_ref}</code>
                    </td>
                    <td className="px-4 py-3 text-xs text-cns-muted">{fmtWhen(profile.last_used_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => openEdit(profile)}
                          className="text-xs font-semibold text-emerald-700 hover:underline dark:text-emerald-400"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void onValidate(profile)}
                          className="text-xs font-semibold text-zinc-700 hover:underline dark:text-zinc-300"
                        >
                          Validate
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void onDelete(profile)}
                          className="text-xs font-semibold text-red-700 hover:underline dark:text-red-400"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
