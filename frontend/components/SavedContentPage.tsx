import { ContentCard } from "@/components/ContentCard";
import { EmptyState } from "@/components/EmptyState";
import type { Content } from "@/types/content";

type SavedContentPageProps = {
  title: string;
  subtitle: string;
  badgeText: string;
  items: Content[];
  emptyTitle: string;
  emptyMessage: string;
};

export function SavedContentPage({
  title,
  subtitle,
  badgeText,
  items,
  emptyTitle,
  emptyMessage,
}: SavedContentPageProps) {
  const itemLabel = items.length === 1 ? "title" : "titles";

  return (
    <main className="saved-page">
      <section className="saved-hero">
        <span className="eyebrow">{badgeText}</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </section>

      <section className="saved-results" aria-labelledby="saved-results-heading">
        <div className="saved-results__header">
          <div>
            <span className="section-label">Saved content</span>
            <h2 id="saved-results-heading">{title}</h2>
          </div>
          <div className="saved-results__meta">
            <strong>{items.length}</strong>
            <span>{itemLabel}</span>
          </div>
        </div>

        {items.length > 0 ? (
          <div className="content-grid saved-grid">
            {items.map((content) => (
              <ContentCard key={content.id} content={content} />
            ))}
          </div>
        ) : (
          <EmptyState title={emptyTitle} message={emptyMessage} />
        )}
      </section>
    </main>
  );
}
