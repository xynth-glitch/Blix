import type { Freshness } from "@/lib/api";

const LABEL: Record<Freshness, string> = {
  live: "Live",
  stale: "Stale",
  scheduled: "Scheduled",
  unknown: "Unknown",
};

export function FreshnessBadge({ freshness }: { freshness: Freshness }) {
  const cls =
    freshness === "live"
      ? "live"
      : freshness === "stale"
        ? "stale"
        : "scheduled";
  return <span className={`badge ${cls}`}>{LABEL[freshness]}</span>;
}
