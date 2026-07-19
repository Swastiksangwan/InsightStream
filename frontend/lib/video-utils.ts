import type { ContentVideo } from "@/types/content";

const YOUTUBE_KEY_PATTERN = /^[A-Za-z0-9_-]{6,64}$/;
const SAFE_EMBED_HOST = "www.youtube-nocookie.com";
const SAFE_WATCH_HOSTS = new Set(["www.youtube.com", "youtube.com"]);

function hasSafeYouTubeIdentity(video: ContentVideo) {
  return (
    video.is_playable === true &&
    video.site.trim().toLowerCase() === "youtube" &&
    YOUTUBE_KEY_PATTERN.test(video.source_video_id)
  );
}

function parseHttpsUrl(value: string | null) {
  if (!value) {
    return null;
  }

  try {
    const url = new URL(value);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.port
    ) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

export function isSafeYouTubeVideo(video: ContentVideo) {
  if (!hasSafeYouTubeIdentity(video)) {
    return false;
  }

  const embedUrl = parseHttpsUrl(video.embed_url);
  if (!embedUrl || embedUrl.hostname !== SAFE_EMBED_HOST) {
    return false;
  }

  const expectedPath = `/embed/${video.source_video_id}`;
  return (
    embedUrl.pathname === expectedPath ||
    embedUrl.pathname.startsWith(`${expectedPath}/`)
  );
}

export function getSafeEmbedUrl(video: ContentVideo, autoplay = false) {
  if (!isSafeYouTubeVideo(video)) {
    return null;
  }

  const url = new URL(
    `https://${SAFE_EMBED_HOST}/embed/${video.source_video_id}`,
  );
  url.searchParams.set("rel", "0");
  if (autoplay) {
    url.searchParams.set("autoplay", "1");
  }
  return url.toString();
}

export function getSafeWatchUrl(video: ContentVideo) {
  if (!hasSafeYouTubeIdentity(video)) {
    return null;
  }

  const watchUrl = parseHttpsUrl(video.watch_url);
  if (
    !watchUrl ||
    !SAFE_WATCH_HOSTS.has(watchUrl.hostname) ||
    watchUrl.pathname !== "/watch" ||
    watchUrl.searchParams.get("v") !== video.source_video_id
  ) {
    return null;
  }

  return `https://www.youtube.com/watch?v=${video.source_video_id}`;
}

export function hasSameVideoIdentity(
  left: ContentVideo,
  right: ContentVideo,
) {
  return (
    left.site.trim().toLowerCase() === right.site.trim().toLowerCase() &&
    left.source_video_id === right.source_video_id
  );
}

export function getSafeVideoCollection(
  videos: ContentVideo[],
  primaryVideo: ContentVideo | null,
) {
  const orderedVideos = primaryVideo ? [primaryVideo, ...videos] : videos;
  const seen = new Set<string>();

  return orderedVideos.filter((video) => {
    if (!isSafeYouTubeVideo(video)) {
      return false;
    }

    const identity = `${video.site.trim().toLowerCase()}:${video.source_video_id}`;
    if (seen.has(identity)) {
      return false;
    }

    seen.add(identity);
    return true;
  });
}

export function getVideoActionLabel(video: ContentVideo) {
  const type = video.type?.trim().toLowerCase();
  if (type === "trailer") {
    return "Watch Trailer";
  }
  if (type === "teaser") {
    return "Watch Teaser";
  }
  return "Watch Video";
}

export function getVideoTypeLabel(video: ContentVideo) {
  const type = video.type?.trim().toLowerCase();
  if (type === "trailer") {
    return "Trailer";
  }
  if (type === "teaser") {
    return "Teaser";
  }
  return "Video";
}

export function getVideoDisplayName(video: ContentVideo) {
  const name = video.name?.trim();
  if (name) {
    return name;
  }
  const type = getVideoTypeLabel(video);
  return video.official ? `Official ${type}` : type;
}

export function getVideoLanguageLabel(languageCode: string | null) {
  const normalized = languageCode?.trim().toLowerCase();
  if (!normalized || !/^[a-z]{2,3}$/.test(normalized)) {
    return null;
  }

  try {
    if (typeof Intl.DisplayNames === "function") {
      const displayNames = new Intl.DisplayNames(["en"], { type: "language" });
      return displayNames.of(normalized) || normalized.toUpperCase();
    }
  } catch {
    // Fall through to a stable language-code label.
  }

  return normalized.toUpperCase();
}

export function getSafeYouTubeThumbnailUrl(video: ContentVideo) {
  if (!isSafeYouTubeVideo(video)) {
    return null;
  }
  return `https://i.ytimg.com/vi/${video.source_video_id}/hqdefault.jpg`;
}
