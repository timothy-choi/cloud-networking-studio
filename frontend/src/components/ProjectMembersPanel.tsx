import { useCallback, useEffect, useState } from 'react';
import { formatApiError } from '../api/client';
import {
  inviteProjectMember,
  listProjectMembers,
  patchProjectMemberRole,
  removeProjectMember,
  type ProjectMemberResponse,
  type ProjectMemberRole,
} from '../api/projectMembers';

function roleBadgeClass(role: ProjectMemberRole): string {
  switch (role) {
    case 'owner':
      return 'bg-violet-100 text-violet-900 ring-violet-600/20 dark:bg-violet-950/60 dark:text-violet-200 dark:ring-violet-500/30';
    case 'member':
      return 'bg-sky-100 text-sky-900 ring-sky-600/20 dark:bg-sky-950/50 dark:text-sky-200 dark:ring-sky-500/30';
    default:
      return 'bg-zinc-100 text-zinc-700 ring-zinc-500/20 dark:bg-zinc-800 dark:text-zinc-300 dark:ring-zinc-500/25';
  }
}

export function ProjectMembersPanel(props: {
  projectId: string | null;
  myRole: ProjectMemberRole | null | undefined;
  onChanged?: () => void;
}) {
  const { projectId, myRole, onChanged } = props;
  const [members, setMembers] = useState<ProjectMemberResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'member' | 'viewer'>('member');
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteErr, setInviteErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setErr(null);
    try {
      setMembers(await listProjectMembers(projectId));
    } catch (e) {
      setErr(formatApiError(e));
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const isOwner = myRole === 'owner';

  if (!projectId) return null;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Project members</h2>
        {myRole ? (
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${roleBadgeClass(myRole)}`}
          >
            Your role: {myRole}
          </span>
        ) : null}
      </div>
      <p className="mt-1 text-xs text-cns-muted">
        {isOwner
          ? 'Invite teammates by email. Owners manage roles and membership.'
          : 'People with access to this workspace. Only owners can invite or change roles.'}
      </p>

      {isOwner ? (
        <div className="mt-4 flex flex-wrap items-end gap-2 border-b border-zinc-100 pb-4 dark:border-zinc-800">
          <label className="min-w-[12rem] flex-1 text-xs font-medium text-zinc-800 dark:text-zinc-200">
            Email
            <input
              type="email"
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="colleague@company.com"
              autoComplete="email"
            />
          </label>
          <label className="text-xs font-medium text-zinc-800 dark:text-zinc-200">
            Role
            <select
              className="mt-1 block w-full min-w-[7rem] rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as 'member' | 'viewer')}
            >
              <option value="member">Member</option>
              <option value="viewer">Viewer</option>
            </select>
          </label>
          <button
            type="button"
            disabled={inviteBusy}
            onClick={() => {
              void (async () => {
                const em = inviteEmail.trim();
                if (!em) {
                  setInviteErr('Enter an email address.');
                  return;
                }
                setInviteBusy(true);
                setInviteErr(null);
                try {
                  await inviteProjectMember(projectId, { email: em, role: inviteRole });
                  setInviteEmail('');
                  await load();
                  onChanged?.();
                } catch (e) {
                  setInviteErr(formatApiError(e));
                } finally {
                  setInviteBusy(false);
                }
              })();
            }}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
          >
            {inviteBusy ? 'Inviting…' : 'Invite'}
          </button>
        </div>
      ) : null}
      {inviteErr ? <p className="mt-2 text-xs text-red-600 dark:text-red-400">{inviteErr}</p> : null}

      {err ? <p className="mt-3 text-sm text-red-600 dark:text-red-400">{err}</p> : null}
      {loading ? <p className="mt-3 text-xs text-cns-muted">Loading members…</p> : null}

      {!loading && members.length <= 1 ? (
        <p className="mt-4 rounded-lg border border-dashed border-zinc-200 bg-zinc-50/80 px-4 py-6 text-center text-sm text-cns-muted dark:border-zinc-700 dark:bg-zinc-950/40">
          No team members yet.
        </p>
      ) : null}

      {!loading && members.length > 0 ? (
        <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-800">
          {members.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-3 first:pt-0">
              <div className="min-w-0">
                <div className="font-medium text-zinc-900 dark:text-zinc-100">{m.display_name}</div>
                <div className="truncate font-mono text-xs text-cns-muted">{m.email}</div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {isOwner ? (
                  <select
                    className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
                    value={m.role}
                    onChange={(e) => {
                      const next = e.target.value as ProjectMemberRole;
                      void (async () => {
                        try {
                          await patchProjectMemberRole(projectId, m.id, { role: next });
                          await load();
                          onChanged?.();
                        } catch (ex) {
                          alert(formatApiError(ex));
                          await load();
                        }
                      })();
                    }}
                  >
                    <option value="viewer">viewer</option>
                    <option value="member">member</option>
                    <option value="owner">owner</option>
                  </select>
                ) : (
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${roleBadgeClass(m.role)}`}
                  >
                    {m.role}
                  </span>
                )}
                {isOwner ? (
                  <button
                    type="button"
                    className="text-xs font-medium text-red-700 hover:underline dark:text-red-400"
                    onClick={() => {
                      if (!window.confirm(`Remove ${m.display_name} from this project?`)) return;
                      void (async () => {
                        try {
                          await removeProjectMember(projectId, m.id);
                          await load();
                          onChanged?.();
                        } catch (ex) {
                          alert(formatApiError(ex));
                        }
                      })();
                    }}
                  >
                    Remove
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
