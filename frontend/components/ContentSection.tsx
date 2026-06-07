import { ContentCard } from "@/components/ContentCard";
import { EmptyState } from "@/components/EmptyState";
import type { Content } from "@/types/content";

type ContentSectionProps = {
  title: string;
  eyebrow?: string;
  description?: string;
  items: Content[];
  emptyMessage: string;
};

export function ContentSection({
  title,
  eyebrow = "InsightStream",
  description,
  items,
  emptyMessage,
}: ContentSectionProps) {
  return (
    <section className="content-section" aria-labelledby={`${title}-heading`}>
      <div className="content-section__header">
        <div>
          <span className="section-label">{eyebrow}</span>
          <h2 id={`${title}-heading`}>{title}</h2>
        </div>
        <div className="content-section__meta">
          {description ? <p>{description}</p> : null}
          <span>{items.length} shown</span>
        </div>
      </div>

      {items.length > 0 ? (
        <div className="content-grid">
          {items.map((content) => (
            <ContentCard key={content.id} content={content} />
          ))}
        </div>
      ) : (
        <EmptyState message={emptyMessage} />
      )}
    </section>
  );
}
