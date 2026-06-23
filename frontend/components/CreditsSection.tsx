import { PersonCreditCard } from "@/components/PersonCreditCard";
import type {
  ContentCreditsResponse,
  CreditCastMember,
  CreditCrewMember,
} from "@/types/credits";

type CreditsSectionProps = {
  credits?: ContentCreditsResponse | null;
};

type CrewDisplayMember = {
  person_id: number;
  name: string;
  profile_url?: string | null;
  subtitle: string;
  sortPriority: number;
};

const CREW_LIMIT = 12;
const CREW_ROLE_PRIORITY = new Map([
  ["Creator", 1],
  ["Director", 2],
  ["Writer", 3],
  ["Screenplay", 4],
  ["Story", 5],
  ["Producer", 6],
  ["Executive Producer", 7],
]);

function castSubtitle(member: CreditCastMember) {
  return member.character_name || "Cast";
}

function titleCaseRole(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function roleTypeLabel(roleType?: string | null) {
  if (roleType === "director") {
    return "Director";
  }

  if (roleType === "creator") {
    return "Creator";
  }

  if (roleType === "crew") {
    return "Crew";
  }

  return roleType ? titleCaseRole(roleType) : null;
}

function crewLabel(member: CreditCrewMember) {
  if (member.job?.trim()) {
    return member.job.trim();
  }

  const roleLabel = roleTypeLabel(member.role_type);
  if (roleLabel) {
    return roleLabel;
  }

  if (member.department?.trim()) {
    return titleCaseRole(member.department.trim());
  }

  return "Crew";
}

function crewLabelPriority(label: string) {
  return CREW_ROLE_PRIORITY.get(label) ?? 99;
}

function buildCrewDisplayMembers(
  credits: ContentCreditsResponse,
): CrewDisplayMember[] {
  const combinedCrew = [
    ...credits.crew,
    ...credits.directors.map((person) => ({
      ...person,
      role_type: person.role_type || "director",
    })),
    ...credits.creators.map((person) => ({
      ...person,
      role_type: person.role_type || "creator",
    })),
  ];
  const byPerson = new Map<
    number,
    {
      person_id: number;
      name: string;
      profile_url?: string | null;
      labels: Set<string>;
      sortPriority: number;
    }
  >();

  for (const member of combinedCrew) {
    const label = crewLabel(member);
    const priority = crewLabelPriority(label);
    const existing = byPerson.get(member.person_id);

    if (existing) {
      existing.labels.add(label);
      existing.sortPriority = Math.min(existing.sortPriority, priority);
      if (!existing.profile_url && member.profile_url) {
        existing.profile_url = member.profile_url;
      }
      continue;
    }

    byPerson.set(member.person_id, {
      person_id: member.person_id,
      name: member.name,
      profile_url: member.profile_url,
      labels: new Set([label]),
      sortPriority: priority,
    });
  }

  return Array.from(byPerson.values())
    .map((member) => ({
      person_id: member.person_id,
      name: member.name,
      profile_url: member.profile_url,
      subtitle: Array.from(member.labels)
        .sort((left, right) => {
          const priorityDiff = crewLabelPriority(left) - crewLabelPriority(right);
          return priorityDiff || left.localeCompare(right);
        })
        .slice(0, 3)
        .join(", "),
      sortPriority: member.sortPriority,
    }))
    .sort((left, right) => {
      const priorityDiff = left.sortPriority - right.sortPriority;
      return priorityDiff || left.name.localeCompare(right.name);
    })
    .slice(0, CREW_LIMIT);
}

export function CreditsSection({ credits }: CreditsSectionProps) {
  if (!credits) {
    return null;
  }

  const cast = credits.cast.slice(0, 10);
  const crew = buildCrewDisplayMembers(credits);

  return (
    <section className="credits-section" aria-label="Cast and credits">
      <div className="credits-section__header">
        <span className="section-label">People</span>
        <h2>Cast &amp; Crew</h2>
        <p>Key people behind this title.</p>
      </div>

      <div className="credits-subsection">
        <div className="credits-subsection__header">
          <h3>Top Cast</h3>
        </div>

        {cast.length > 0 ? (
          <div
            className="credits-rail credits-rail--cast"
            role="list"
            aria-label="Top cast"
          >
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
        ) : (
          <p className="credits-empty-state">No cast data is available yet.</p>
        )}
      </div>

      <div className="credits-subsection credits-subsection--creative">
        <div className="credits-subsection__header">
          <h3>Crew</h3>
        </div>

        {crew.length > 0 ? (
          <div
            className="credits-rail credits-rail--crew"
            role="list"
            aria-label="Crew"
          >
            {crew.map((person) => (
              <div
                className="credits-rail__item credits-rail__item--compact"
                role="listitem"
                key={`crew-${person.person_id}`}
              >
                <PersonCreditCard
                  name={person.name}
                  subtitle={person.subtitle}
                  profileUrl={person.profile_url}
                  href={`/people/${person.person_id}`}
                  variant="compact"
                />
              </div>
            ))}
          </div>
        ) : (
          <p className="credits-empty-state">No key crew data is available yet.</p>
        )}
      </div>
    </section>
  );
}
