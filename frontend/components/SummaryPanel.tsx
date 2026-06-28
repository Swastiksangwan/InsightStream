import type { InsightSummary } from "@/types/content";

type SummaryPanelProps = {
  summary?: InsightSummary | null;
};

function hasInsightSummary(summary?: InsightSummary | null): summary is InsightSummary {
  if (!summary) {
    return false;
  }

  const bestFor = summary.best_for ?? [];
  const keySignals = summary.key_signals ?? [];

  return Boolean(
    summary.headline ||
      summary.summary ||
      bestFor.length > 0 ||
      keySignals.length > 0 ||
      summary.watch_note,
  );
}

export function SummaryPanel({ summary }: SummaryPanelProps) {
  if (!hasInsightSummary(summary)) {
    return (
      <section className="detail-panel detail-panel--wide">
        <div className="detail-panel__header">
          <span className="section-label">Decision support</span>
          <h2>Insight Summary</h2>
        </div>
        <p className="detail-empty">Not enough structured data to generate a summary yet.</p>
      </section>
    );
  }

  const bestFor = summary.best_for ?? [];
  const keySignals = summary.key_signals ?? [];

  return (
    <section className="detail-panel detail-panel--wide">
      <div className="detail-panel__header">
        <span className="section-label">Decision support</span>
        <h2>Insight Summary</h2>
      </div>

      {summary.headline ? (
        <h3 className="insight-summary__headline">{summary.headline}</h3>
      ) : null}
      {summary.summary ? <p className="insight-summary__body">{summary.summary}</p> : null}

      {bestFor.length > 0 ? (
        <div className="insight-summary__group">
          <h3>Best for</h3>
          <div className="insight-summary__chips">
            {bestFor.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        </div>
      ) : null}

      {keySignals.length > 0 ? (
        <div className="insight-summary__group">
          <h3>Decision signals</h3>
          <ul className="insight-summary__signals">
            {keySignals.map((signal) => (
              <li key={`${signal.label}-${signal.value}`}>
                <span>{signal.label}</span>
                <strong>{signal.value}</strong>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {summary.watch_note ? (
        <div className="insight-summary__group">
          <h3>Consider first</h3>
          <p className="insight-summary__note">{summary.watch_note}</p>
        </div>
      ) : null}
    </section>
  );
}
