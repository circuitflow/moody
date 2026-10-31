export function signed(x: number, digits = 2): string {
  return (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(digits);
}

export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Index of the segment covering time t (segments are sorted by start). */
export function segmentAt(starts: readonly number[], t: number): number {
  let lo = 0;
  let hi = starts.length - 1;
  if (hi < 0) return -1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (starts[mid]! <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** The 2007 tree's thresholds and branch names (moody.legacy.thesis2007.THRESHOLDS). */
export const THESIS_FEATURES = [
  { key: "mode", label: "Mode", threshold: 50, high: "major", low: "minor" },
  { key: "harmony", label: "Harmony", threshold: 75, high: "simple", low: "complex" },
  { key: "tempo", label: "Tempo", threshold: 40, high: "fast", low: "slow" },
  { key: "rhythm", label: "Rhythm", threshold: 65, high: "regular", low: "irregular" },
  { key: "loudness", label: "Loudness", threshold: 50, high: "loud", low: "soft" },
] as const;
