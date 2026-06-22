import { LoadingState } from "@/components/LoadingState";

export default function SearchLoading() {
  return (
    <main className="search-page">
      <section className="search-hero">
        <span className="eyebrow">Local Search</span>
        <h1>Search results</h1>
        <p>Loading local catalog matches from InsightStream.</p>
      </section>

      <LoadingState message="Searching local catalog..." />
    </main>
  );
}
