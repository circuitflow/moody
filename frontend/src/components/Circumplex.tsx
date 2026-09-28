/**
 * Placeholder for the M2 mood map: Russell's circumplex with the eight octants used by the
 * 2007 thesis (see legacy/README.md), counter-clockwise from positive valence.
 */
const OCTANTS = [
  "Pleasure",
  "Excitement",
  "Arousal",
  "Distress",
  "Displeasure",
  "Depression",
  "Sleepiness",
  "Relaxation",
] as const;

const R = 38;

export function Circumplex() {
  return (
    <svg className="circumplex" viewBox="0 0 100 100" role="img" aria-label="Valence–arousal mood space">
      <circle cx="50" cy="50" r={R - 8} />
      <line x1="4" y1="50" x2="96" y2="50" />
      <line x1="50" y1="4" x2="50" y2="96" />
      {OCTANTS.map((label, i) => {
        const theta = (i * Math.PI) / 4;
        return (
          <text
            key={label}
            x={50 + R * Math.cos(theta)}
            y={50 - R * Math.sin(theta)}
            textAnchor="middle"
            dominantBaseline="middle"
            className="octant"
          >
            {label}
          </text>
        );
      })}
      <text x="97" y="57" textAnchor="end" className="axis">valence →</text>
      <text x="52" y="6" className="axis">↑ arousal</text>
    </svg>
  );
}
