export function StreamingIndicator() {
  return (
    <span aria-label="Assistant is responding" className="inline-flex gap-1">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-3"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}
