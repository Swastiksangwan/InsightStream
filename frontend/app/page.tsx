import { Suspense } from "react";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { HomeBucketSection } from "@/components/HomeBucketSection";
import { HomePosterRail } from "@/components/HomePosterRail";
import { LoadingState } from "@/components/LoadingState";
import { getHomeContent } from "@/lib/api";
import type { HomeQuickFilter, HomeSection } from "@/types/content";

const HOME_SECTION_LIMIT = 8;

function quickFilterHref(filter: HomeQuickFilter) {
  if (filter.filter_key === "top_rated") {
    return "#top_rated";
  }

  if (
    filter.filter_key === "fast_paced" ||
    filter.filter_key === "dark_intense" ||
    filter.filter_key === "light_comfort"
  ) {
    return "#mood_pace";
  }

  return "#home-sections";
}

function formatGeneratedFor(value?: string | null) {
  if (!value) {
    return null;
  }

  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function hasRenderableContent(section: HomeSection) {
  if (section.section_type === "bucketed_rail") {
    return (section.buckets ?? []).some((bucket) => bucket.items.length > 0);
  }

  return (section.items ?? []).length > 0;
}

function HomeSectionBlock({ section }: { section: HomeSection }) {
  if (!hasRenderableContent(section)) {
    return null;
  }

  return (
    <section
      className="home-section"
      id={section.section_id}
      aria-labelledby={`${section.section_id}-heading`}
    >
      <div className="home-section__header">
        <div>
          <h2 id={`${section.section_id}-heading`}>{section.title}</h2>
        </div>
        <p>{section.subtitle}</p>
      </div>

      {section.section_type === "bucketed_rail" ? (
        <HomeBucketSection buckets={section.buckets ?? []} />
      ) : (
        <HomePosterRail items={section.items ?? []} />
      )}
    </section>
  );
}

async function HomepageContent() {
  try {
    const home = await getHomeContent(HOME_SECTION_LIMIT);
    const sections = home.sections.filter(hasRenderableContent);
    const generatedFor = formatGeneratedFor(home.generated_for);

    return (
      <>
        <section className="home-hero" aria-label="Homepage decision hub">
          <div className="home-hero__copy">
            <div className="eyebrow">Movies and series decision support</div>
            <h1>{home.hero.title}</h1>
            <p>{home.hero.subtitle}</p>

            {home.hero.quick_filters.length > 0 ? (
              <div className="home-quick-filters" aria-label="Quick filters">
                {home.hero.quick_filters.map((filter) => (
                  <a key={filter.filter_key} href={quickFilterHref(filter)}>
                    {filter.label}
                  </a>
                ))}
              </div>
            ) : null}
          </div>

          <div className="home-hero__panel" aria-label="Refresh information">
            <span>Homepage intelligence</span>
            <strong>{generatedFor ? `Updated for ${generatedFor}` : "Updated daily"}</strong>
            <p>Daily rails refresh automatically. Weekly picks refresh every week.</p>
          </div>
        </section>

        {sections.length > 0 ? (
          <div className="home-sections" id="home-sections">
            {sections.map((section) => (
              <HomeSectionBlock key={section.section_id} section={section} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="No homepage picks yet"
            message="Homepage sections will appear here once the backend has display-ready titles."
          />
        )}
      </>
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to load homepage content from the backend.";

    return (
      <ErrorState
        title="Could not load homepage"
        message={`${message} Make sure the FastAPI backend is running at the configured API URL.`}
      />
    );
  }
}

export default function HomePage() {
  return (
    <main className="home-page">
      <Suspense fallback={<LoadingState message="Loading InsightStream picks..." />}>
        <HomepageContent />
      </Suspense>
    </main>
  );
}
