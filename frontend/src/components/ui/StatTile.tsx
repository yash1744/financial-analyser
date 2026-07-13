import { Card } from "./Card";
import { Skeleton } from "./Skeleton";

/** KPI tile: label + big value + optional sub-line. */
export function StatTile({
  label,
  value,
  sub,
  subTone = "neutral",
  loading = false,
}: {
  label: string;
  value: string;
  sub?: string;
  subTone?: "neutral" | "good" | "bad";
  loading?: boolean;
}) {
  const subColor =
    subTone === "good"
      ? "text-good"
      : subTone === "bad"
        ? "text-bad"
        : "text-ink-3";
  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-wide text-ink-3">
        {label}
      </p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-28" />
      ) : (
        <p className="mt-1 text-2xl font-semibold text-ink">{value}</p>
      )}
      {sub && !loading && (
        <p className={`mt-1 text-xs ${subColor}`}>{sub}</p>
      )}
    </Card>
  );
}
