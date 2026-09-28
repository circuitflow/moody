/** Placeholder for the M2 mood map: Russell's valence/arousal circumplex with quadrant labels. */
const QUADRANTS = [
  { x: 25, y: 25, label: "tense · angry" },
  { x: 75, y: 25, label: "happy · excited" },
  { x: 25, y: 75, label: "sad · gloomy" },
  { x: 75, y: 75, label: "calm · relaxed" },
] as const;

export function Circumplex() {
  return (
    <svg className="circumplex" viewBox="0 0 100 100" role="img" aria-label="Valence–arousal mood space">
      <line x1="0" y1="50" x2="100" y2="50" />
      <line x1="50" y1="0" x2="50" y2="100" />
      <text x="98" y="47" textAnchor="end" className="axis">valence →</text>
      <text x="52" y="4" className="axis">↑ arousal</text>
      {QUADRANTS.map((q) => (
        <text key={q.label} x={q.x} y={q.y} textAnchor="middle" className="quadrant">
          {q.label}
        </text>
      ))}
    </svg>
  );
}
