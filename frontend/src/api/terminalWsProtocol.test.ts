import { describe, expect, it } from 'vitest';
import {
  classifyTerminalWsMessage,
  filterTerminalFrame,
  normalizeTerminalFrame,
  parseTerminalControlFrame,
} from './terminalWsProtocol';

describe('normalizeTerminalFrame', () => {
  it('drops pong and other control frames', () => {
    expect(normalizeTerminalFrame('{"type":"pong"}')).toBeNull();
    expect(normalizeTerminalFrame('{"type":"ping"}')).toBeNull();
    expect(normalizeTerminalFrame('{"type":"heartbeat"}')).toBeNull();
    expect(normalizeTerminalFrame('{"type":"keepalive"}')).toBeNull();
    expect(normalizeTerminalFrame('{"type":"connected"}')).toBeNull();
    expect(normalizeTerminalFrame('\r\n{"type":"pong"}\r\n')).toBeNull();
  });

  it('unwraps terminal_data envelopes', () => {
    expect(normalizeTerminalFrame('{"type":"terminal_data","data":"hello"}')).toBe('hello');
  });

  it('passes plain terminal output through', () => {
    expect(normalizeTerminalFrame('hello')).toBe('hello');
    expect(normalizeTerminalFrame('$ ls\r\n')).toBe('$ ls\r\n');
  });

  it('matches filterTerminalFrame alias', () => {
    expect(filterTerminalFrame('{"type":"pong"}')).toBeNull();
    expect(filterTerminalFrame('hello')).toBe('hello');
  });
});

describe('parseTerminalControlFrame', () => {
  it('parses error with message', () => {
    expect(parseTerminalControlFrame('{"type":"error","message":"boom"}')).toEqual({
      type: 'error',
      message: 'boom',
    });
  });
});

describe('classifyTerminalWsMessage', () => {
  it('treats UTF-8 binary pong as control', () => {
    const bytes = new TextEncoder().encode('{"type":"pong"}');
    const payload = classifyTerminalWsMessage(bytes.buffer);
    expect(payload.kind).toBe('control');
  });
});
