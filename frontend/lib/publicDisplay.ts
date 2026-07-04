const BLOCKED_PUBLIC_PATTERNS = [
  /tmdb_keywords/i,
  /source_names/i,
  /mapping_version/i,
  /provider keyword/i,
  /source_signal/i,
  /jiohotstar viewers/i,
  /netflix viewers/i,
  /prime video viewers/i,
  /serialized drama viewers/i,
  /platform viewers/i,
  /availability viewers/i,
];

const COMPACT_DISPLAY_PLATFORM_PATTERNS = [
  /\bjiohotstar\b/i,
  /\bnetflix\b/i,
  /\bprime video\b/i,
  /\bamazon prime video\b/i,
];

type PublicTextOptions = {
  blockPlatformNames?: boolean;
};

export function cleanPublicText(
  value?: string | null,
  options: PublicTextOptions = {},
) {
  if (!value) {
    return null;
  }

  const cleaned = value.replace(/\s+/g, " ").trim();
  if (!cleaned) {
    return null;
  }

  if (BLOCKED_PUBLIC_PATTERNS.some((pattern) => pattern.test(cleaned))) {
    return null;
  }

  if (
    options.blockPlatformNames &&
    COMPACT_DISPLAY_PLATFORM_PATTERNS.some((pattern) => pattern.test(cleaned))
  ) {
    return null;
  }

  return cleaned;
}

export function cleanPublicList(
  values?: Array<string | null | undefined> | null,
  options: PublicTextOptions = {},
) {
  const seen = new Set<string>();
  const output: string[] = [];

  for (const value of values ?? []) {
    const cleaned = cleanPublicText(value, options);
    if (!cleaned) {
      continue;
    }

    const key = cleaned.toLowerCase();
    if (seen.has(key)) {
      continue;
    }

    seen.add(key);
    output.push(cleaned);
  }

  return output;
}
