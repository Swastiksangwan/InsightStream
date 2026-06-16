import { PersonCreditCard } from "@/components/PersonCreditCard";
import type {
  ContentCreditsResponse,
  CreditCastMember,
  CreditCrewMember,
} from "@/types/credits";

type CreditsSectionProps = {
  credits?: ContentCreditsResponse | null;
};

function hasCredits(credits?: ContentCreditsResponse | null) {
  return Boolean(
    credits &&
      (credits.cast.length > 0 ||
        credits.directors.length > 0 ||
        credits.creators.length > 0 ||
        credits.crew.length > 0),
  );
}

function castSubtitle(member: CreditCastMember) {
  return member.character_name || "Cast";
}

function crewSubtitle(member: CreditCrewMember, fallback: string) {
  if (member.job && member.department && member.job !== member.department) {
    return `${member.job} / ${member.department}`;
  }

  return member.job || member.department || fallback;
}

export function CreditsSection({ credits }: CreditsSectionProps) {
  if (!hasCredits(credits)) {
    return null;
  }

  const cast = credits?.cast.slice(0, 5) || [];
  const directors = credits?.directors || [];
  const creators = credits?.creators || [];
  const crew = credits?.crew || [];
  const keyPeople = [
    ...directors.map((person) => ({
      ...person,
      fallback: "Director",
    })),
    ...creators.map((person) => ({
      ...person,
      fallback: "Creator",
    })),
  ];
  const keyPeopleHeading =
    directors.length && creators.length
      ? "Creative Credits"
      : directors.length
        ? directors.length > 1
          ? "Directors"
          : "Director"
        : creators.length > 1
          ? "Creators"
          : "Creator";

  return (
    <section className="credits-section" aria-label="Cast and credits">
      <div className="credits-section__header">
        <span className="section-label">People</span>
        <h2>Cast &amp; Crew</h2>
        <p>Key people behind this title.</p>
      </div>

      {cast.length > 0 ? (
        <div className="credits-subsection">
          <div className="credits-subsection__header">
            <h3>Top Cast</h3>
          </div>

          <div className="credits-rail" role="list" aria-label="Top cast">
            {cast.map((member) => (
              <div
                className="credits-rail__item"
                role="listitem"
                key={`cast-${member.person_id}`}
              >
                <PersonCreditCard
                  name={member.name}
                  subtitle={castSubtitle(member)}
                  profileUrl={member.profile_url}
                  href={`/people/${member.person_id}`}
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {keyPeople.length > 0 ? (
        <div className="credits-subsection credits-subsection--creative">
          <div className="credits-subsection__header">
            <h3>{keyPeopleHeading}</h3>
          </div>

          <div className="credits-rail credits-rail--compact" role="list">
            {keyPeople.map((person) => (
              <div
                className="credits-rail__item credits-rail__item--compact"
                role="listitem"
                key={`${person.fallback}-${person.person_id}`}
              >
                <PersonCreditCard
                  name={person.name}
                  subtitle={crewSubtitle(person, person.fallback)}
                  profileUrl={person.profile_url}
                  href={`/people/${person.person_id}`}
                  variant="compact"
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {crew.length > 0 ? (
        <div className="credits-subsection credits-subsection--creative">
          <div className="credits-subsection__header">
            <h3>Crew</h3>
          </div>

          <div className="credits-rail credits-rail--compact" role="list">
            {crew.map((person) => (
              <div
                className="credits-rail__item credits-rail__item--compact"
                role="listitem"
                key={`crew-${person.person_id}-${person.job || "role"}`}
              >
                <PersonCreditCard
                  name={person.name}
                  subtitle={crewSubtitle(person, "Crew")}
                  profileUrl={person.profile_url}
                  href={`/people/${person.person_id}`}
                  variant="compact"
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
