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
export const TERMINAL_CONTROL_TYPES = new Set<string>([
  'ping',
  'pong',
  'connected',
  'error',
  'heartbeat',
  'keepalive',
]);

const TERMINAL_DEBUG =
  typeof import.meta !== 'undefined' && Boolean(import.meta.env?.DEV);

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
  if (!TERMINAL_CONTROL_TYPES.has(kind)) return null;
  return {
    type: kind as TerminalControlType,
    message: typeof parsed.message === 'string' ? parsed.message : undefined,
  };
}

/**
 * Normalize a WebSocket text frame for xterm output.
 *
 * - Control JSON (ping, pong, …) → null (never print)
 * - ``terminal_data`` envelope → inner data string
 * - Plain shell output → original string
 */
export function normalizeTerminalFrame(raw: string): string | null {
  const parsed = tryParseJsonObject(raw);
  if (parsed) {
    const kind = frameType(parsed);
    if (kind === 'terminal_data') {
      const data = parsed.data;
      return typeof data === 'string' ? data : '';
    }
    if (TERMINAL_CONTROL_TYPES.has(kind)) {
      if (TERMINAL_DEBUG) {
        console.debug('filtered control frame', kind);
      }
      return null;
    }
  }
  return raw;
}

/** @deprecated use normalizeTerminalFrame */
export const filterTerminalFrame = normalizeTerminalFrame;

export type TerminalWsPayload =
  | { kind: 'control'; frame: TerminalControlFrame }
  | { kind: 'output'; data: string | Uint8Array };

function classifyTextPayload(text: string): TerminalWsPayload {
  const frame = parseTerminalControlFrame(text);
  if (frame) return { kind: 'control', frame };

  const out = normalizeTerminalFrame(text);
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

export type TerminalWriteHandlers = {
  onControl: (frame: TerminalControlFrame) => void;
};

/**
 * Single entry point for writing WebSocket payloads to xterm.
 * Returns true when terminal output was written.
 */
export function writeTerminalWsPayload(
  terminal: { write: (data: string | Uint8Array) => void },
  data: string | ArrayBuffer,
  handlers: TerminalWriteHandlers,
): boolean {
  const text =
    typeof data === 'string' ? data : new TextDecoder().decode(new Uint8Array(data));

  if (TERMINAL_DEBUG) {
    console.debug('terminal frame', text.slice(0, 240));
  }

  const control = parseTerminalControlFrame(text);
  if (control) {
    handlers.onControl(control);
    return false;
  }

  const normalized = normalizeTerminalFrame(text);
  if (normalized === null) {
    return false;
  }

  if (typeof data === 'string') {
    terminal.write(normalized);
    return true;
  }
  if (normalized !== text) {
    terminal.write(normalized);
    return true;
  }
  terminal.write(new Uint8Array(data));
  return true;
}
