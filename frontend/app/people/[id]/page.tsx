import Link from "next/link";
import { ErrorState } from "@/components/ErrorState";
import { PersonFilmographyCard } from "@/components/PersonFilmographyCard";
import { PersonProfileHero } from "@/components/PersonProfileHero";
import {
  ApiRequestError,
  getPerson,
  getPersonCredits,
} from "@/lib/api";
import type { PersonCreditItem, PersonCreditsResponse } from "@/types/people";

type PersonDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

type FilmographyGroup = {
  key: keyof Pick<PersonCreditsResponse, "cast" | "directed" | "created" | "crew">;
  title: string;
  description: string;
  getRoleLabel: (item: PersonCreditItem) => string;
};

function emptyCredits(personId: number): PersonCreditsResponse {
  return {
    person_id: personId,
    cast: [],
    directed: [],
    created: [],
    crew: [],
  };
}

function hasCredits(credits: PersonCreditsResponse) {
  return (
    credits.cast.length > 0 ||
    credits.directed.length > 0 ||
    credits.created.length > 0 ||
    credits.crew.length > 0
  );
}

function crewRoleLabel(item: PersonCreditItem) {
  if (item.job && item.department && item.job !== item.department) {
    return `${item.job} / ${item.department}`;
  }

  return item.job || item.department || "Crew";
}

const filmographyGroups: FilmographyGroup[] = [
  {
    key: "cast",
    title: "Known For / Cast",
    description: "Acting credits connected to the current catalog.",
    getRoleLabel: (item) => (item.character_name ? `as ${item.character_name}` : "Cast"),
  },
  {
    key: "directed",
    title: "Directed",
    description: "Titles directed by this person.",
    getRoleLabel: (item) => item.job || "Director",
  },
  {
    key: "created",
    title: "Created",
    description: "Series or titles created by this person.",
    getRoleLabel: (item) => item.job || "Creator",
  },
  {
    key: "crew",
    title: "Crew",
    description: "Additional credited work in the current catalog.",
    getRoleLabel: crewRoleLabel,
  },
];

export default async function PersonDetailPage({ params }: PersonDetailPageProps) {
  const { id } = await params;
  const personId = Number(id);

  if (!Number.isInteger(personId) || personId <= 0) {
    return (
      <main className="person-page">
        <ErrorState
          title="Invalid person"
          message="This person page could not be loaded because the person ID is invalid."
        />
      </main>
    );
  }

  try {
    const person = await getPerson(personId);
    const creditsResult = await Promise.allSettled([getPersonCredits(personId)]);
    const credits =
      creditsResult[0].status === "fulfilled"
        ? creditsResult[0].value
        : emptyCredits(person.person_id);
    const creditsLoadError =
      creditsResult[0].status === "rejected"
        ? "Filmography could not be loaded right now."
        : null;

    return (
      <main className="person-page">
        <section className="person-hero">
          <div className="person-hero__wash" aria-hidden="true" />
          <Link className="detail-back-link" href="/discover">
            Back to discovery
          </Link>
          <PersonProfileHero person={person} />
        </section>

        <section className="person-page-grid" aria-label="Person details">
          <section className="person-panel person-biography">
            <div className="detail-section-heading">
              <span className="section-label">Profile</span>
              <h2>Biography</h2>
            </div>
            {person.biography ? (
              <p>{person.biography}</p>
            ) : (
              <p className="detail-empty">Biography not available yet.</p>
            )}
          </section>

          <section className="person-panel person-filmography">
            <div className="person-filmography__header">
              <div>
                <span className="section-label">Credits</span>
                <h2>Filmography</h2>
                <p>Related titles currently available in InsightStream.</p>
              </div>
            </div>

            {creditsLoadError ? (
              <p className="detail-empty">{creditsLoadError}</p>
            ) : null}

            {!creditsLoadError && !hasCredits(credits) ? (
              <p className="detail-empty">No catalog credits are available yet.</p>
            ) : null}

            {filmographyGroups.map((group) => {
              const items = credits[group.key];

              if (items.length === 0) {
                return null;
              }

              return (
                <section
                  className="person-credit-group"
                  key={group.key}
                  aria-labelledby={`person-${group.key}-heading`}
                >
                  <div className="person-credit-group__header">
                    <h3 id={`person-${group.key}-heading`}>{group.title}</h3>
                    <p>{group.description}</p>
                  </div>

                  <div className="person-filmography-grid">
                    {items.map((item) => (
                      <PersonFilmographyCard
                        item={item}
                        key={`${group.key}-${item.content_id}-${item.character_name || item.job || "credit"}`}
                        roleLabel={group.getRoleLabel(item)}
                      />
                    ))}
                  </div>
                </section>
              );
            })}
          </section>
        </section>
      </main>
    );
  } catch (error) {
    const isNotFound = error instanceof ApiRequestError && error.status === 404;
    const message = isNotFound
      ? "This person could not be found in the current InsightStream catalog."
      : error instanceof Error
        ? error.message
        : "Unable to load this person page.";

    return (
      <main className="person-page">
        <ErrorState
          title={isNotFound ? "Person not found" : "Could not load person"}
          message={message}
        />
      </main>
    );
  }
}
