import { ScoreBadge } from "@/components/ScoreBadge";
import type { Summary } from "@/types/content";

type SummaryPanelProps = {
  summary?: Summary | null;
};

export function SummaryPanel({ summary }: SummaryPanelProps) {
  if (!summary) {
    return (
      <section className="detail-panel detail-panel--wide">
        <div className="detail-panel__header">
          <span className="section-label">Decision support</span>
          <h2>Insight Summary</h2>
        </div>
        <p className="detail-empty">No InsightStream summary is available yet.</p>
      </section>
    );
  }

  return (
    <section className="detail-panel detail-panel--wide">
      <div className="detail-panel__header">
        <span className="section-label">Decision support</span>
        <h2>Insight Summary</h2>
      </div>

      <div className="score-grid">
        <ScoreBadge label="Unified" value={summary.unified_score} tone="primary" />
        <ScoreBadge label="Critic" value={summary.critic_score} tone="critic" />
        <ScoreBadge label="Audience" value={summary.audience_score} tone="audience" />
      </div>

      <div className="summary-copy">
        <h3>Review Signal</h3>
        <p>{summary.review_summary || "No review summary is available yet."}</p>
      </div>

      <div className="summary-columns">
        <div>
          <h3>Pros</h3>
          <p>{summary.pros || "No pros have been summarized yet."}</p>
        </div>
        <div>
          <h3>Cons</h3>
          <p>{summary.cons || "No cons have been summarized yet."}</p>
        </div>
        <div>
          <h3>Verdict</h3>
          <p>{summary.verdict || "No verdict is available yet."}</p>
        </div>
      </div>
    </section>
  );
}
