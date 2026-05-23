import { getImageCapabilities } from '../../lib/imageCapabilities';

export function ImageCapabilityHints({
  image,
  command,
}: {
  image: string;
  command: string;
}) {
  if (!image.trim()) return null;
  const caps = getImageCapabilities(image, command);
  if (caps.hints.length === 0) return null;
  return (
    <div className="rounded-md border border-amber-800/40 bg-amber-950/20 px-2 py-2 text-[10px] leading-snug text-amber-100/90">
      <p className="font-medium text-amber-200/90">Image capabilities ({caps.profile})</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-4">
        {caps.hints.map((h) => (
          <li key={h}>{h}</li>
        ))}
      </ul>
      {caps.missingByDefault.length > 0 ? (
        <p className="mt-1 text-amber-200/70">
          Often missing until bootstrap: {caps.missingByDefault.join(', ')}
        </p>
      ) : null}
    </div>
  );
}
