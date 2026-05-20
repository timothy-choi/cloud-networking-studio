import { describe, expect, it } from 'vitest';
import {
  classifyTerminalWsMessage,
  filterTerminalFrame,
  parseTerminalControlFrame,
} from './terminalWsProtocol';

describe('filterTerminalFrame', () => {
  it('drops heartbeat control frames', () => {
    expect(filterTerminalFrame('{"type":"pong"}')).toBeNull();
    expect(filterTerminalFrame('{"type":"ping"}')).toBeNull();
    expect(filterTerminalFrame('{"type":"heartbeat"}')).toBeNull();
    expect(filterTerminalFrame('{"type":"keepalive"}')).toBeNull();
    expect(filterTerminalFrame('\r\n{"type":"pong"}\r\n')).toBeNull();
  });

  it('passes plain terminal output through', () => {
    expect(filterTerminalFrame('hello')).toBe('hello');
    expect(filterTerminalFrame('$ ls\r\n')).toBe('$ ls\r\n');
  });

  it('unwraps terminal_data envelopes', () => {
    expect(filterTerminalFrame('{"type":"terminal_data","data":"root@host:~# "}')).toBe(
      'root@host:~# ',
    );
  });
});

describe('parseTerminalControlFrame', () => {
  it('parses error with message', () => {
    expect(parseTerminalControlFrame('{"type":"error","message":"boom"}')).toEqual({
      type: 'error',
      message: 'boom',
    });
  });

  it('returns null for shell output', () => {
    expect(parseTerminalControlFrame('$ ls')).toBeNull();
  });
});

describe('classifyTerminalWsMessage', () => {
  it('treats UTF-8 binary pong as control', () => {
    const bytes = new TextEncoder().encode('{"type":"pong"}');
    const payload = classifyTerminalWsMessage(bytes.buffer);
    expect(payload.kind).toBe('control');
  });

  it('passes binary shell bytes through as output', () => {
    const bytes = new Uint8Array([0x1b, 0x5b, 0x41]);
    const payload = classifyTerminalWsMessage(bytes.buffer);
    expect(payload.kind).toBe('output');
    if (payload.kind === 'output') {
      expect(payload.data).toBeInstanceOf(Uint8Array);
    }
  });
});
