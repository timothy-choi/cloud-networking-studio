import { describe, expect, it } from 'vitest';
import {
  classifyTerminalWsMessage,
  parseTerminalControlFrame,
} from './terminalWsProtocol';

describe('parseTerminalControlFrame', () => {
  it('parses pong and ping', () => {
    expect(parseTerminalControlFrame('{"type":"pong"}')).toEqual({ type: 'pong' });
    expect(parseTerminalControlFrame('\r\n{"type":"ping"}\r\n')).toEqual({ type: 'ping' });
  });

  it('parses error with message', () => {
    expect(parseTerminalControlFrame('{"type":"error","message":"boom"}')).toEqual({
      type: 'error',
      message: 'boom',
    });
  });

  it('returns null for shell output', () => {
    expect(parseTerminalControlFrame('$ ls')).toBeNull();
    expect(parseTerminalControlFrame('hello world')).toBeNull();
  });
});

describe('classifyTerminalWsMessage', () => {
  it('treats UTF-8 binary pong as control', () => {
    const bytes = new TextEncoder().encode('{"type":"pong"}');
    const payload = classifyTerminalWsMessage(bytes.buffer);
    expect(payload.kind).toBe('control');
    if (payload.kind === 'control') {
      expect(payload.frame.type).toBe('pong');
    }
  });

  it('passes binary shell bytes through as output', () => {
    const bytes = new Uint8Array([0x1b, 0x5b, 0x41]);
    const payload = classifyTerminalWsMessage(bytes.buffer);
    expect(payload.kind).toBe('output');
  });
});
