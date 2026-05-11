import type { ReactNode } from 'react';

/** Side-by-side shell for the topology canvas and inspector panels. */
export function TopologyStudioLayout({
  canvas,
  sidebar,
}: {
  canvas: ReactNode;
  sidebar: ReactNode;
}) {
  return (
    <div className="flex min-h-[560px] flex-col gap-3 xl:flex-row">
      <div className="min-h-[520px] min-w-0 flex-1">{canvas}</div>
      <div className="flex w-full shrink-0 flex-col gap-3 xl:w-[380px]">{sidebar}</div>
    </div>
  );
}
