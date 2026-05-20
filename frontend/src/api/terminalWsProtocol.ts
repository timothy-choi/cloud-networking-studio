/** WebSocket control frames for the interactive terminal (not TTY output). */

export type TerminalControlType = 'ping' | 'pong' | 'connected' | 'error';

export type TerminalControlFrame = {
  type: TerminalControlType;
  message?: string;
};

const CONTROL_TYPES = new Set<string>(['ping', 'pong', 'connected', 'error']);

/**
 * Parse a JSON control frame from a WebSocket text payload.
 * Returns null when the payload is shell output (not a control frame).
 */
export function parseTerminalControlFrame(raw: string): TerminalControlFrame | null {
  const trimmed = raw.trim();
  if (!trimmed.includes('"type"')) return null;

  const start = trimmed.indexOf('{');
  const end = trimmed.lastIndexOf('}');
  if (start === -1 || end === -1 || end <= start) return null;

  try {
    const parsed = JSON.parse(trimmed.slice(start, end + 1)) as {
      type?: unknown;
      message?: unknown;
    };
    const kind = typeof parsed.type === 'string' ? parsed.type.trim().toLowerCase() : '';
    if (!CONTROL_TYPES.has(kind)) return null;
    return {
      type: kind as TerminalControlType,
      message: typeof parsed.message === 'string' ? parsed.message : undefined,
    };
  } catch {
    return null;
  }
}

export type TerminalWsPayload =
  | { kind: 'control'; frame: TerminalControlFrame }
  | { kind: 'output'; data: string | Uint8Array };

/** Classify a WebSocket message as control traffic or terminal output. */
export function classifyTerminalWsMessage(data: string | ArrayBuffer): TerminalWsPayload {
  if (typeof data === 'string') {
    const frame = parseTerminalControlFrame(data);
    if (frame) return { kind: 'control', frame };
    return { kind: 'output', data };
  }

  const bytes = new Uint8Array(data);
  const text = new TextDecoder().decode(bytes);
  const frame = parseTerminalControlFrame(text);
  if (frame) return { kind: 'control', frame };
  return { kind: 'output', data: bytes };
}
