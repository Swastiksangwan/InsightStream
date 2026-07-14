import { cleanPublicList, cleanPublicText } from "@/lib/publicDisplay";
import type { DecisionDisplay, DecisionDisplayFact } from "@/types/content";

type DecisionDisplayCardProps = {
  display?: DecisionDisplay | null;
};

type ChipGroupProps = {
  label: string;
  items: string[];
  variant?: "muted" | "accent";
};

function cleanDisplayList(values?: string[], limit = 4) {
  return cleanPublicList(values, { blockPlatformNames: true }).slice(0, limit);
}

function cleanDisplayFact(fact: DecisionDisplayFact) {
  const label = cleanPublicText(fact.label, { blockPlatformNames: true });
  const value = cleanPublicText(fact.value, { blockPlatformNames: true });

  if (!label || !value) {
    return null;
  }

  return { label, value };
}

function getDisplayParts(display?: DecisionDisplay | null) {
  const profile = display?.profile ?? null;
  const primaryInsight = cleanPublicText(display?.primary_insight, {
    blockPlatformNames: true,
  });
  const identity = cleanDisplayList(profile?.identity, 3);
  const themes = cleanDisplayList(profile?.themes, 3);
  const feel = cleanDisplayList(profile?.feel, 3);
  const pace = cleanPublicText(profile?.pace, { blockPlatformNames: true });
  const bestFor = cleanDisplayList(profile?.best_for, 2);
  const considerFirst = cleanDisplayList(profile?.consider_first, 1);
  const facts = (display?.supporting_facts ?? [])
    .map(cleanDisplayFact)
    .filter((fact): fact is DecisionDisplayFact => Boolean(fact))
    .slice(0, 4);

  return {
    primaryInsight,
    identity,
    themes,
    feel,
    pace,
    bestFor,
    considerFirst,
    facts,
  };
}

export function hasDecisionDisplay(display?: DecisionDisplay | null) {
  const parts = getDisplayParts(display);

  return Boolean(
    parts.primaryInsight ||
      parts.identity.length > 0 ||
      parts.themes.length > 0 ||
      parts.feel.length > 0 ||
      parts.pace ||
      parts.bestFor.length > 0 ||
      parts.considerFirst.length > 0 ||
      parts.facts.length > 0,
  );
}

function ChipGroup({ label, items, variant = "muted" }: ChipGroupProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="decision-display__group">
      <h3>{label}</h3>
      <div className={`decision-display__chips decision-display__chips--${variant}`}>
        {items.map((item) => (
          <span key={`${label}-${item}`}>{item}</span>
        ))}
      </div>
    </div>
  );
}

export function DecisionDisplayCard({ display }: DecisionDisplayCardProps) {
  const parts = getDisplayParts(display);

  if (!hasDecisionDisplay(display)) {
    return null;
  }

  return (
    <section className="detail-panel detail-panel--wide decision-display">
      {parts.primaryInsight ? (
        <div className="decision-display__lead">
          <h2>Why this stands out</h2>
          <p>{parts.primaryInsight}</p>
        </div>
      ) : null}

      <div className="decision-display__profile" aria-label="Decision profile">
        <ChipGroup label="Identity" items={parts.identity} variant="accent" />
        <ChipGroup label="Themes" items={parts.themes} />
        <ChipGroup label="Feel" items={parts.feel} />

        {parts.pace ? (
          <div className="decision-display__group">
            <h3>Pace</h3>
            <p className="decision-display__pace">{parts.pace}</p>
          </div>
        ) : null}

        <ChipGroup label="Best for" items={parts.bestFor} />
      </div>

      {parts.considerFirst.length > 0 ? (
        <div className="decision-display__consider">
          <h3>Consider first</h3>
          <p>{parts.considerFirst[0]}</p>
        </div>
      ) : null}

      {parts.facts.length > 0 ? (
        <div className="decision-display__facts">
          <h3>At a glance</h3>
          <dl>
            {parts.facts.map((fact) => (
              <div key={`${fact.label}-${fact.value}`}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </section>
  );
}
