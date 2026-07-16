export default function SearchLoading() {
  return (
    <main className="search-page">
      <section className="search-panel" aria-busy="true" aria-live="polite">
        <div className="search-tabs search-tabs--loading">
          <span />
          <span />
        </div>

        <section className="search-results-section">
          <div className="search-results-section__header">
            <span className="search-skeleton search-skeleton--heading" />
            <span className="search-skeleton search-skeleton--count" />
          </div>
          <div className="search-title-grid">
            {Array.from({ length: 8 }).map((_, index) => (
              <div className="search-title-card search-title-card--skeleton" key={index}>
                <span className="search-skeleton search-skeleton--poster" />
                <span className="search-skeleton search-skeleton--title" />
                <span className="search-skeleton search-skeleton--meta" />
              </div>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
