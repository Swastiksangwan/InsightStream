type ScoreBadgeProps = {
  label: string;
  value?: number | null;
  tone?: "primary" | "critic" | "audience" | "general";
};

function formatScore(value?: number | null) {
  if (value === null || value === undefined) {
    return "NR";
  }

  return Math.round(value).toString();
}

export function ScoreBadge({ label, value, tone = "primary" }: ScoreBadgeProps) {
  return (
    <div className={`score-badge score-badge--${tone}`}>
      <span>{label}</span>
      <strong>{formatScore(value)}</strong>
      <small>/100</small>
    </div>
  );
}
