import { ContentCard } from "@/components/ContentCard";
import type { Content } from "@/types/content";

type ContentSectionProps = {
  title: string;
  description?: string;
  items: Content[];
  emptyMessage: string;
};

export function ContentSection({
  title,
  description,
  items,
  emptyMessage,
}: ContentSectionProps) {
  return (
    <section className="content-section" aria-labelledby={`${title}-heading`}>
      <div className="content-section__header">
        <div>
          <span className="section-label">InsightStream</span>
          <h2 id={`${title}-heading`}>{title}</h2>
        </div>
        {description ? <p>{description}</p> : null}
      </div>

      {items.length > 0 ? (
        <div className="content-grid">
          {items.map((content) => (
            <ContentCard key={content.id} content={content} />
          ))}
        </div>
      ) : (
        <div className="empty-state">{emptyMessage}</div>
      )}
    </section>
  );
}
