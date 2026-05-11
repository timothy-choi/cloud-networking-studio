import type { ReactNode } from 'react';

/**
 * Studio shell: graph column grows with a tall min-height; sidebar stacks inspector panels.
 * Parents must not use overflow-hidden — graph uses an explicit height for React Flow.
 */
export function TopologyStudioLayout({
  canvas,
  sidebar,
}: {
  canvas: ReactNode;
  sidebar: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 xl:flex-row xl:items-stretch xl:gap-4">
      <div className="order-1 flex min-h-0 min-w-0 flex-1 flex-col">{canvas}</div>
      <div className="order-2 flex w-full shrink-0 flex-col gap-3 xl:order-2 xl:w-[min(100%,380px)] xl:max-w-[400px] xl:shrink-0">
        {sidebar}
      </div>
    </div>
  );
}
