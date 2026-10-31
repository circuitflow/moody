/** Horizontal bars for a handful of probabilities: one series color, values in text ink. */
export function Bars({ items, label }: { items: [string, number][]; label: string }) {
  return (
    <figure className="bars" aria-label={label}>
      <figcaption>{label}</figcaption>
      <ul>
        {items.map(([name, p]) => (
          <li key={name}>
            <span className="bar-label">{name}</span>
            <span className="bar-track">
              <span className="bar-fill" style={{ width: `${Math.max(0, Math.min(1, p)) * 100}%` }} />
            </span>
            <span className="bar-value num">{Math.round(p * 100)}%</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
