type EmptyStateProps = {
  title?: string;
  message: string;
};

export function EmptyState({
  title = "No content found",
  message,
}: EmptyStateProps) {
  return (
    <section className="empty-state empty-state--center">
      <h2>{title}</h2>
      <p>{message}</p>
    </section>
  );
}
