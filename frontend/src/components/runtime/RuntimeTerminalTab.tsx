import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, formatApiError } from '../../api/client';
import {
  closeTerminalSession,
  createTerminalSession,
  terminalWebSocketUrl,
} from '../../api/runtimeTerminal';
import {
  writeTerminalWsPayload,
  type TerminalControlFrame,
} from '../../api/terminalWsProtocol';
import type { RuntimeAccessResourceRow } from '../../types/runtime';
import { isTerminalEnabledForResource } from '../../lib/nodeRuntimeConfig';

type ConnState = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error';

const QUICK_COMMANDS = [
  { label: 'hostname', cmd: 'hostname' },
  { label: 'ip addr', cmd: 'ip addr' },
  { label: 'ip route', cmd: 'ip route' },
  { label: 'resolv.conf', cmd: 'cat /etc/resolv.conf' },
] as const;

function connLabel(state: ConnState): string {
  switch (state) {
    case 'connecting':
      return 'Connecting…';
    case 'connected':
      return 'Connected';
    case 'disconnected':
      return 'Disconnected';
    case 'reconnecting':
      return 'Reconnecting…';
    case 'error':
      return 'Error';
    default:
      return 'Not connected';
  }
}

function connBadgeClass(state: ConnState): string {
  switch (state) {
    case 'connected':
      return 'bg-emerald-900/50 text-emerald-200';
    case 'connecting':
    case 'reconnecting':
      return 'bg-amber-900/50 text-amber-200';
    case 'error':
      return 'bg-red-900/50 text-red-200';
    default:
      return 'bg-zinc-800 text-zinc-300';
  }
}

export function RuntimeTerminalTab({
  deploymentId,
  services,
  readOnly,
}: {
  deploymentId: string;
  services: RuntimeAccessResourceRow[];
  readOnly?: boolean;
}) {
  const [serviceId, setServiceId] = useState('');
  const [connState, setConnState] = useState<ConnState>('idle');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sessionRef = useRef<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const serviceIdRef = useRef(serviceId);
  const intentionalCloseRef = useRef(false);
  const onDataDisposeRef = useRef<(() => void) | null>(null);

  const selectable = services.filter((s) => s.id && isTerminalEnabledForResource(s.metadata ?? undefined));

  useEffect(() => {
    serviceIdRef.current = serviceId;
  }, [serviceId]);

  useEffect(() => {
    if (!serviceId && selectable[0]?.id) setServiceId(selectable[0].id);
  }, [serviceId, selectable]);

  const teardown = useCallback(async (closeSession: boolean) => {
    intentionalCloseRef.current = true;
    onDataDisposeRef.current?.();
    onDataDisposeRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
    if (closeSession && sessionRef.current) {
      try {
        await closeTerminalSession(sessionRef.current);
      } catch {
        /* ignore */
      }
      sessionRef.current = null;
    }
    setConnState('disconnected');
    intentionalCloseRef.current = false;
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      theme: {
        background: '#09090b',
        foreground: '#e4e4e7',
        cursor: '#a1a1aa',
      },
      scrollback: 5000,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host);
    fit.fit();
    term.writeln('Select a service and press Connect.');

    termRef.current = term;
    fitRef.current = fit;

    const onResize = () => {
      try {
        fit.fit();
        const ws = wsRef.current;
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(
            JSON.stringify({
              type: 'resize',
              cols: term.cols,
              rows: term.rows,
            }),
          );
        }
      } catch {
        /* ignore */
      }
    };
    window.addEventListener('resize', onResize);
    const ro = new ResizeObserver(onResize);
    ro.observe(host);

    return () => {
      window.removeEventListener('resize', onResize);
      ro.disconnect();
      void teardown(true);
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
    };
  }, [teardown]);

  function applyControlFrame(frame: TerminalControlFrame, ws: WebSocket): void {
    switch (frame.type) {
      case 'ping':
        ws.send(JSON.stringify({ type: 'pong' }));
        break;
      case 'pong':
        break;
      case 'connected':
        setConnState('connected');
        if (frame.message) {
          setErr(null);
        }
        break;
      case 'error':
        setConnState('error');
        setErr(frame.message ?? 'Terminal error');
        break;
      default:
        break;
    }
  }

  const connect = useCallback(
    async (mode: 'connect' | 'reconnect' = 'connect') => {
      if (readOnly) {
        setErr('Viewers cannot open interactive terminals.');
        return;
      }
      const sid = serviceIdRef.current;
      if (!sid) {
        setErr('Select a service resource row.');
        return;
      }

      if (wsRef.current) {
        await teardown(true);
      }

      setBusy(true);
      setErr(null);
      setConnState(mode === 'reconnect' ? 'reconnecting' : 'connecting');
      intentionalCloseRef.current = false;

      const term = termRef.current;
      if (term) {
        term.clear();
        term.writeln(mode === 'reconnect' ? 'Reconnecting…' : 'Connecting…');
      }

      try {
        const session = await createTerminalSession(deploymentId, sid);
        sessionRef.current = session.session_id;
        if (session.message && term) {
          term.writeln(session.message);
        }

        const ws = new WebSocket(terminalWebSocketUrl(session.websocket_path));
        ws.binaryType = 'arraybuffer';
        wsRef.current = ws;

        ws.onopen = () => {
          setConnState('connected');
          setBusy(false);
          const t = termRef.current;
          const f = fitRef.current;
          if (t && f) {
            f.fit();
            ws.send(
              JSON.stringify({
                type: 'resize',
                cols: t.cols,
                rows: t.rows,
              }),
            );
          }
          if (termRef.current) {
            const disposable = termRef.current.onData((data) => {
              if (ws.readyState === WebSocket.OPEN) {
                ws.send(data);
              }
            });
            onDataDisposeRef.current = () => disposable.dispose();
          }
        };

        ws.onmessage = (ev) => {
          const t = termRef.current;
          if (!t) return;
          writeTerminalWsPayload(t, ev.data as string | ArrayBuffer, {
            onControl: (frame) => applyControlFrame(frame, ws),
          });
        };

        ws.onclose = (ev) => {
          onDataDisposeRef.current?.();
          onDataDisposeRef.current = null;
          wsRef.current = null;
          if (!intentionalCloseRef.current) {
            setConnState('disconnected');
            const code = ev.code ? ` (${ev.code})` : '';
            termRef.current?.writeln(
              `\r\n\x1b[33m[disconnected${code}]\x1b[0m — use Reconnect or Connect again.`,
            );
          }
          setBusy(false);
        };

        ws.onerror = () => {
          setConnState('error');
          setErr('WebSocket connection failed.');
          termRef.current?.writeln('\r\n\x1b[31m[connection error]\x1b[0m');
          setBusy(false);
        };
      } catch (e) {
        setConnState('error');
        setErr(e instanceof ApiError ? formatApiError(e) : 'Could not open terminal.');
        termRef.current?.writeln('\r\n\x1b[31mFailed to open terminal session.\x1b[0m');
        setBusy(false);
      }
    },
    [deploymentId, readOnly, teardown],
  );

  async function disconnect() {
    await teardown(true);
    termRef.current?.writeln('\r\n[session closed]');
  }

  function runQuickCommand(cmd: string) {
    const ws = wsRef.current;
    const term = termRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !term) return;
    term.write(`\r\n$ ${cmd}\r\n`);
    ws.send(`${cmd}\r`);
  }

  function runCurlQuick() {
    const row = selectable.find((s) => s.id === serviceId);
    const url = row?.internal_url?.trim();
    if (!url) {
      setErr('No internal URL on this service row — use Mapping or Services tab.');
      return;
    }
    runQuickCommand(`curl -fsS ${url}`);
  }

  const connected = connState === 'connected';

  return (
    <div className="space-y-3">
      <p className="text-xs text-cns-muted">
        Interactive shell inside the workload (advanced). Safe exec remains available for allowlisted
        diagnostics. Members and owners only. Sessions idle-timeout and are audited on the server.
      </p>
      {readOnly ? (
        <p className="text-sm text-amber-800 dark:text-amber-200">You have viewer access; terminal is disabled.</p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${connBadgeClass(connState)}`}
        >
          {connLabel(connState)}
        </span>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-cns-label">
          Service
          <select
            className="mt-1 block w-64 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            value={serviceId}
            onChange={(e) => setServiceId(e.target.value)}
            disabled={connected || readOnly}
          >
            <option value="">—</option>
            {selectable.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.runtime_name})
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={busy || connected || readOnly || !serviceId}
          onClick={() => void connect('connect')}
          className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
        >
          {busy && connState === 'connecting' ? 'Connecting…' : 'Connect'}
        </button>
        <button
          type="button"
          disabled={busy || readOnly || !serviceId || connected}
          onClick={() => void connect('reconnect')}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium hover:bg-zinc-50 dark:border-zinc-600 dark:hover:bg-zinc-800 disabled:opacity-50"
        >
          Reconnect
        </button>
        <button
          type="button"
          disabled={!connected && connState !== 'error'}
          onClick={() => void disconnect()}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium hover:bg-zinc-50 dark:border-zinc-600 dark:hover:bg-zinc-800 disabled:opacity-50"
        >
          Disconnect
        </button>
      </div>

      <div className="flex flex-wrap gap-1">
        {QUICK_COMMANDS.map((q) => (
          <button
            key={q.label}
            type="button"
            disabled={!connected}
            onClick={() => runQuickCommand(q.cmd)}
            className="rounded border border-zinc-600 px-2 py-0.5 font-mono text-[10px] text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
          >
            {q.label}
          </button>
        ))}
        <button
          type="button"
          disabled={!connected || !selectable.find((s) => s.id === serviceId)?.internal_url}
          onClick={() => runCurlQuick()}
          className="rounded border border-zinc-600 px-2 py-0.5 font-mono text-[10px] text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
        >
          curl service
        </button>
      </div>

      {err ? <p className="text-sm text-red-700 dark:text-red-300">{err}</p> : null}

      <div
        ref={hostRef}
        className="h-64 w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 p-1"
        aria-label="Terminal"
      />
    </div>
  );
}
