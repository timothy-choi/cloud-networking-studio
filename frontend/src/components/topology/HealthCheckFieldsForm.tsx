import {
  DEBUG_TOOLBOX_HINT,
  emptyHealthCheckFields,
  HEALTH_CHECK_TYPE_LABELS,
  inferHealthWarnings,
  readHealthCheckFields,
  type HealthCheckFields,
  type HealthCheckType,
} from '../../lib/healthCheckConfig';

export interface HealthCheckFieldsFormProps {
  image: string;
  command: string;
  healthCheckRaw: unknown;
  value: HealthCheckFields;
  onChange: (fields: HealthCheckFields) => void;
}

export function healthCheckFieldsFromRaw(
  raw: unknown,
  image: string,
): HealthCheckFields {
  const fields = readHealthCheckFields(raw);
  if (raw == null || raw === '') {
    const il = image.toLowerCase();
    if (il.includes('nginx') || il.includes('httpd')) {
      return { ...fields, check_type: 'http', port: '80', path: '/' };
    }
    if (il.includes('redis')) {
      return { ...fields, check_type: 'tcp', port: '6379' };
    }
    if (il.includes('postgres')) {
      return { ...fields, check_type: 'tcp', port: '5432' };
    }
    return { ...emptyHealthCheckFields(), check_type: 'runtime' };
  }
  return fields;
}

export function HealthCheckFieldsForm({
  image,
  command,
  healthCheckRaw,
  value,
  onChange,
}: HealthCheckFieldsFormProps) {
  const warnings = inferHealthWarnings(image, command, value);

  return (
    <fieldset className="space-y-2 rounded-md border border-zinc-700/80 p-2">
      <legend className="px-1 text-[11px] font-medium text-cns-field-label">Health check</legend>
      <label className="block text-[11px] text-cns-field-label">
        Check type
        <select
          className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100"
          value={value.check_type}
          onChange={(ev) =>
            onChange({ ...value, check_type: ev.target.value as HealthCheckType })
          }
        >
          {(Object.keys(HEALTH_CHECK_TYPE_LABELS) as HealthCheckType[]).map((t) => (
            <option key={t} value={t}>
              {HEALTH_CHECK_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
      </label>
      {value.check_type === 'tcp' || value.check_type === 'http' ? (
        <label className="block text-[11px] text-cns-field-label">
          Port
          <input
            className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
            value={value.port}
            onChange={(ev) => onChange({ ...value, port: ev.target.value })}
            placeholder={value.check_type === 'http' ? '80' : '6379'}
          />
        </label>
      ) : null}
      {value.check_type === 'http' ? (
        <>
          <label className="block text-[11px] text-cns-field-label">
            Path
            <input
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
              value={value.path}
              onChange={(ev) => onChange({ ...value, path: ev.target.value })}
              placeholder="/"
            />
          </label>
          <label className="block text-[11px] text-cns-field-label">
            Expected status
            <input
              className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
              value={value.expected_status}
              onChange={(ev) => onChange({ ...value, expected_status: ev.target.value })}
              placeholder="200"
            />
          </label>
        </>
      ) : null}
      {value.check_type === 'command' ? (
        <label className="block text-[11px] text-cns-field-label">
          Command
          <input
            className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
            value={value.command}
            onChange={(ev) => onChange({ ...value, command: ev.target.value })}
            placeholder="redis-cli ping"
          />
        </label>
      ) : null}
      {value.check_type !== 'none' ? (
        <label className="block text-[11px] text-cns-field-label">
          Timeout (ms)
          <input
            className="mt-0.5 w-full rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 font-mono text-sm text-zinc-100"
            value={value.timeout_ms}
            onChange={(ev) => onChange({ ...value, timeout_ms: ev.target.value })}
            placeholder="8000"
          />
        </label>
      ) : null}
      {warnings.length > 0 ? (
        <ul className="space-y-1 text-[10px] leading-snug text-amber-200/90">
          {warnings.map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      ) : null}
      <p className="text-[10px] leading-snug text-zinc-500">{DEBUG_TOOLBOX_HINT}</p>
      {healthCheckRaw != null && healthCheckRaw !== '' ? null : (
        <p className="text-[10px] text-zinc-600">Defaults inferred from image when unset.</p>
      )}
    </fieldset>
  );
}
