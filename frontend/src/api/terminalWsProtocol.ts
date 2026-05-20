/** WebSocket framing for the interactive terminal (control vs TTY output). */

export type TerminalControlType =
  | 'ping'
  | 'pong'
  | 'connected'
  | 'error'
  | 'heartbeat'
  | 'keepalive';

export type TerminalControlFrame = {
  type: TerminalControlType;
  message?: string;
};

/** Control frames — never written to xterm. */
const CONTROL_TYPES = new Set<string>([
  'ping',
  'pong',
  'connected',
  'error',
  'heartbeat',
  'keepalive',
]);

function tryParseJsonObject(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    const start = trimmed.indexOf('{');
    const end = trimmed.lastIndexOf('}');
    if (start === -1 || end === -1 || end <= start) return null;
    try {
      const parsed = JSON.parse(trimmed.slice(start, end + 1)) as unknown;
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return null;
    }
  }
  return null;
}

function frameType(parsed: Record<string, unknown>): string {
  return typeof parsed.type === 'string' ? parsed.type.trim().toLowerCase() : '';
}

/**
 * Parse a JSON control frame. Returns null when the payload is not a control message.
 */
export function parseTerminalControlFrame(raw: string): TerminalControlFrame | null {
  const parsed = tryParseJsonObject(raw);
  if (!parsed) return null;
  const kind = frameType(parsed);
  if (!CONTROL_TYPES.has(kind)) return null;
  return {
    type: kind as TerminalControlType,
    message: typeof parsed.message === 'string' ? parsed.message : undefined,
  };
}

/**
 * Returns terminal text to write to xterm, or null when the frame must not be printed.
 *
 * - Control frames (ping, pong, heartbeat, …) → null
 * - ``{ "type": "terminal_data", "data": "..." }`` → data string
 * - Plain shell output → original string
 */
export function filterTerminalFrame(raw: string): string | null {
  const parsed = tryParseJsonObject(raw);
  if (parsed) {
    const kind = frameType(parsed);
    if (kind === 'terminal_data') {
      const data = parsed.data;
      return typeof data === 'string' ? data : '';
    }
    if (CONTROL_TYPES.has(kind)) {
      return null;
    }
  }
  return raw;
}

export type TerminalWsPayload =
  | { kind: 'control'; frame: TerminalControlFrame }
  | { kind: 'output'; data: string | Uint8Array };

function classifyTextPayload(text: string): TerminalWsPayload {
  const frame = parseTerminalControlFrame(text);
  if (frame) return { kind: 'control', frame };

  const out = filterTerminalFrame(text);
  if (out === null) {
    return { kind: 'control', frame: { type: 'heartbeat' } };
  }
  return { kind: 'output', data: out };
}

/** Classify a WebSocket message as control traffic or terminal output. */
export function classifyTerminalWsMessage(data: string | ArrayBuffer): TerminalWsPayload {
  if (typeof data === 'string') {
    return classifyTextPayload(data);
  }
  const bytes = new Uint8Array(data);
  const text = new TextDecoder().decode(bytes);
  const classified = classifyTextPayload(text);
  if (classified.kind === 'output' && typeof classified.data === 'string' && classified.data !== text) {
    return classified;
  }
  if (classified.kind === 'control') {
    return classified;
  }
  return { kind: 'output', data: bytes };
}
