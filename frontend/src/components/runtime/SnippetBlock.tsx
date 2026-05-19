import type { IntegrationSnippet } from '../../api/runtimeIntegration';
import { CopyButton } from './CopyButton';

export function SnippetBlock({ snippet }: { snippet: IntegrationSnippet }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-950/40">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">{snippet.title}</h4>
          <span className="text-[10px] uppercase tracking-wide text-cns-muted">{snippet.language}</span>
        </div>
        <CopyButton text={snippet.content} />
      </div>
      <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded bg-zinc-950/90 p-2 font-mono text-[11px] text-zinc-100">
        {snippet.content}
      </pre>
    </div>
  );
}
