export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-md bg-line ${className}`} />
  );
}

/** Placeholder block for a loading card: a few grey lines. */
export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={i === 0 ? "h-4 w-1/3" : "h-4 w-full"} />
      ))}
    </div>
  );
}
