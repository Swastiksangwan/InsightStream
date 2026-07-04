import { cleanPublicList, cleanPublicText } from "@/lib/publicDisplay";
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

  const headline = cleanPublicText(summary.headline, { blockPlatformNames: true });
  const body = cleanPublicText(summary.summary, { blockPlatformNames: true });
  const bestFor = cleanPublicList(summary.best_for, {
    blockPlatformNames: true,
  });
  const keySignals = (summary.key_signals ?? [])
    .map((signal) => {
      const label = cleanPublicText(signal.label, { blockPlatformNames: true });
      const isAccessSignal = label?.toLowerCase() === "access";
      const value = cleanPublicText(signal.value, {
        blockPlatformNames: !isAccessSignal,
      });

      if (!label || !value) {
        return null;
      }

      return { label, value };
    })
    .filter((signal): signal is { label: string; value: string } => Boolean(signal));
  const watchNote = cleanPublicText(summary.watch_note, {
    blockPlatformNames: true,
  });

  if (
    !headline &&
    !body &&
    bestFor.length === 0 &&
    keySignals.length === 0 &&
    !watchNote
  ) {
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

  return (
    <section className="detail-panel detail-panel--wide">
      <div className="detail-panel__header">
        <span className="section-label">Decision support</span>
        <h2>Insight Summary</h2>
      </div>

      {headline ? <h3 className="insight-summary__headline">{headline}</h3> : null}
      {body ? <p className="insight-summary__body">{body}</p> : null}

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

      {watchNote ? (
        <div className="insight-summary__group">
          <h3>Consider first</h3>
          <p className="insight-summary__note">{watchNote}</p>
        </div>
      ) : null}
    </section>
  );
}
