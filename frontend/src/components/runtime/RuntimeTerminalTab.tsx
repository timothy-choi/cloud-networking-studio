import { useEffect, useRef, useState } from 'react';
import { ApiError, formatApiError } from '../../api/client';
import {
  closeTerminalSession,
  createTerminalSession,
  terminalWebSocketUrl,
} from '../../api/runtimeTerminal';
import type { RuntimeAccessResourceRow } from '../../types/runtime';
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
  const [connected, setConnected] = useState(false);
  const [log, setLog] = useState<string>('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sessionRef = useRef<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLPreElement>(null);

  const selectable = services.filter((s) => s.id);

  useEffect(() => {
    if (!serviceId && selectable[0]?.id) setServiceId(selectable[0].id);
  }, [serviceId, selectable]);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      if (sessionRef.current) {
        void closeTerminalSession(sessionRef.current).catch(() => undefined);
      }
    };
  }, []);

  function appendLog(chunk: string) {
    setLog((prev) => prev + chunk);
    requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    });
  }

  async function connect() {
    if (readOnly) {
      setErr('Viewers cannot open interactive terminals.');
      return;
    }
    if (!serviceId) {
      setErr('Select a service resource row.');
      return;
    }
    setBusy(true);
    setErr(null);
    setLog('');
    try {
      const session = await createTerminalSession(deploymentId, serviceId);
      sessionRef.current = session.session_id;
      if (session.message) appendLog(session.message + '\r\n');
      const ws = new WebSocket(terminalWebSocketUrl(session.websocket_path));
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => {
        setConnected(true);
        appendLog('[connected]\r\n');
      };
      ws.onmessage = (ev) => {
        if (typeof ev.data === 'string') appendLog(ev.data);
        else if (ev.data instanceof ArrayBuffer) {
          appendLog(new TextDecoder().decode(ev.data));
        }
      };
      ws.onclose = () => {
        setConnected(false);
        appendLog('\r\n[disconnected — reconnect by pressing Connect]\r\n');
      };
      ws.onerror = () => appendLog('\r\n[websocket error]\r\n');
      wsRef.current = ws;
    } catch (e) {
      setErr(e instanceof ApiError ? formatApiError(e) : 'Could not open terminal.');
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    wsRef.current?.close();
    wsRef.current = null;
    setConnected(false);
    if (sessionRef.current) {
      try {
        await closeTerminalSession(sessionRef.current);
      } catch {
        /* ignore */
      }
      sessionRef.current = null;
    }
  }

  function sendInput(text: string) {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(text);
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-cns-muted">
        Interactive shell inside the workload (advanced). Safe exec remains available for allowlisted diagnostics.
        Members and owners only. Sessions idle-timeout and are audited on the server.
      </p>
      {readOnly ? (
        <p className="text-sm text-amber-800 dark:text-amber-200">You have viewer access; terminal is disabled.</p>
      ) : null}
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
          onClick={() => void connect()}
          className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
        >
          {busy ? 'Connecting…' : 'Connect'}
        </button>
        <button
          type="button"
          disabled={!connected}
          onClick={() => void disconnect()}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium hover:bg-zinc-50 dark:border-zinc-600 dark:hover:bg-zinc-800"
        >
          Disconnect
        </button>
      </div>
      {err ? <p className="text-sm text-red-700 dark:text-red-300">{err}</p> : null}
      <pre
        ref={scrollRef}
        className="h-48 overflow-auto rounded-lg border border-zinc-800 bg-zinc-950 p-2 font-mono text-[11px] text-zinc-100"
      >
        {log || '(output appears here)'}
      </pre>
      <div className="flex gap-2">
        <input
          type="text"
          className="flex-1 rounded border border-zinc-300 bg-white px-2 py-1 font-mono text-sm dark:border-zinc-600 dark:bg-zinc-900"
          placeholder="Type command and press Enter"
          disabled={!connected}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              const v = (e.target as HTMLInputElement).value;
              sendInput(v + '\r');
              (e.target as HTMLInputElement).value = '';
            }
          }}
        />
      </div>
    </div>
  );
}
