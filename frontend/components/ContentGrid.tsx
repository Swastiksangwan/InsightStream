import { ContentCard } from "@/components/ContentCard";
import { EmptyState } from "@/components/EmptyState";
import type { Content } from "@/types/content";

type ContentGridProps = {
  items: Content[];
  emptyMessage: string;
};

export function ContentGrid({ items, emptyMessage }: ContentGridProps) {
  if (items.length === 0) {
    return <EmptyState message={emptyMessage} />;
  }

  return (
    <div className="content-grid discovery-grid">
      {items.map((content) => (
        <ContentCard key={content.id} content={content} />
      ))}
    </div>
  );
}
