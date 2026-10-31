import { AGREEMENT_LABELS, type Agreement, type SequentialLegend } from "./colors";
import { fieldLabel } from "./labels";

export type LegendSpec =
  | { kind: "none" }
  | { kind: "sequential"; field: string; legend: SequentialLegend; missing: number }
  | { kind: "categorical"; counts: Record<Agreement, number> };

const fmt = (x: number) => (Math.abs(x) >= 10 ? x.toFixed(0) : x.toFixed(2));

export function MapLegend({ spec }: { spec: LegendSpec }) {
  if (spec.kind === "none") return null;
  if (spec.kind === "sequential") {
    const { colors, thresholds, domain } = spec.legend;
    const edges = [domain[0], ...thresholds, domain[1]];
    return (
      <figure className="legend" aria-label={`Legend: ${fieldLabel(spec.field)}`}>
        <figcaption>{fieldLabel(spec.field)}</figcaption>
        <ul>
          {colors.map((token, i) => (
            <li key={token}>
              <span className="swatch" style={{ background: `var(${token})` }} />
              <span className="num">
                {fmt(edges[i]!)}–{fmt(edges[i + 1]!)}
              </span>
            </li>
          ))}
          {spec.missing > 0 && (
            <li>
              <span className="swatch" style={{ background: "var(--muted)" }} />
              no value ({spec.missing})
            </li>
          )}
        </ul>
      </figure>
    );
  }
  const order: Agreement[] = ["same", "adjacent", "different", "none"];
  const tokens: Record<Agreement, string> = {
    same: "--series-1",
    adjacent: "--series-3",
    different: "--series-2",
    none: "--muted",
  };
  return (
    <figure className="legend" aria-label="Legend: 2007 vs 2026 octant">
      <figcaption>2007 thesis octant vs 2026 octant</figcaption>
      <ul>
        {order.map((k) =>
          spec.counts[k] > 0 ? (
            <li key={k}>
              <span className="swatch" style={{ background: `var(${tokens[k]})` }} />
              {AGREEMENT_LABELS[k]} <span className="num muted">({spec.counts[k]})</span>
            </li>
          ) : null,
        )}
      </ul>
    </figure>
  );
}
