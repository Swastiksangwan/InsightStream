"use client";

import {
  createContext,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  getSafeVideoCollection,
  getSafeEmbedUrl,
  getSafeWatchUrl,
  getSafeYouTubeThumbnailUrl,
  getVideoActionLabel,
  getVideoDisplayName,
  getVideoLanguageLabel,
  getVideoTypeLabel,
  isSafeYouTubeVideo,
} from "@/lib/video-utils";
import type { ContentVideo } from "@/types/content";

type TrailerExperienceContextValue = {
  primaryVideo: ContentVideo | null;
  videos: ContentVideo[];
  openVideo: (video: ContentVideo, trigger: HTMLElement) => void;
};

const TrailerExperienceContext =
  createContext<TrailerExperienceContextValue | null>(null);

function useTrailerExperience() {
  const context = useContext(TrailerExperienceContext);
  if (!context) {
    throw new Error("Trailer components must be inside TrailerExperience.");
  }
  return context;
}

type TrailerExperienceProps = {
  children: ReactNode;
  contentTitle: string;
  primaryVideo: ContentVideo | null;
  videos: ContentVideo[];
};

export function TrailerExperience({
  children,
  contentTitle,
  primaryVideo,
  videos,
}: TrailerExperienceProps) {
  const safePrimaryVideo =
    primaryVideo && isSafeYouTubeVideo(primaryVideo) ? primaryVideo : null;
  const safeVideos = useMemo(
    () => getSafeVideoCollection(videos, safePrimaryVideo),
    [safePrimaryVideo, videos],
  );
  const [activeVideo, setActiveVideo] = useState<ContentVideo | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  const openVideo = useCallback((video: ContentVideo, trigger: HTMLElement) => {
    if (!isSafeYouTubeVideo(video)) {
      return;
    }
    triggerRef.current = trigger;
    setActiveVideo(video);
  }, []);

  const closeVideo = useCallback(() => {
    setActiveVideo(null);
  }, []);

  useEffect(() => {
    const trigger = triggerRef.current;
    if (activeVideo || !trigger) {
      return;
    }

    const timeout = window.setTimeout(() => {
      trigger.focus({ preventScroll: true });
      triggerRef.current = null;
    }, 0);

    return () => window.clearTimeout(timeout);
  }, [activeVideo]);

  const contextValue = useMemo(
    () => ({ primaryVideo: safePrimaryVideo, videos: safeVideos, openVideo }),
    [openVideo, safePrimaryVideo, safeVideos],
  );

  return (
    <TrailerExperienceContext.Provider value={contextValue}>
      {children}
      {activeVideo ? (
        <TrailerModal
          contentTitle={contentTitle}
          video={activeVideo}
          onClose={closeVideo}
        />
      ) : null}
    </TrailerExperienceContext.Provider>
  );
}

export function TrailerHeroAction() {
  const { primaryVideo, openVideo } = useTrailerExperience();
  if (!primaryVideo) {
    return null;
  }

  return (
    <button
      className="trailer-hero-action"
      type="button"
      aria-label={`${getVideoActionLabel(primaryVideo)}: ${getVideoDisplayName(primaryVideo)}`}
      onClick={(event) => openVideo(primaryVideo, event.currentTarget)}
    >
      <span className="trailer-play-icon" aria-hidden="true" />
      {getVideoActionLabel(primaryVideo)}
    </button>
  );
}

export function TrailersAndTeasersSection() {
  const { primaryVideo, videos, openVideo } = useTrailerExperience();
  const railRef = useRef<HTMLDivElement>(null);
  const [canScrollPrevious, setCanScrollPrevious] = useState(false);
  const [canScrollNext, setCanScrollNext] = useState(false);

  const updateRailState = useCallback(() => {
    const rail = railRef.current;
    if (!rail) {
      return;
    }

    const maxScrollLeft = Math.max(0, rail.scrollWidth - rail.clientWidth);
    setCanScrollPrevious(rail.scrollLeft > 4);
    setCanScrollNext(rail.scrollLeft < maxScrollLeft - 4);
  }, []);

  useEffect(() => {
    const rail = railRef.current;
    if (!rail) {
      return;
    }

    const frame = window.requestAnimationFrame(updateRailState);
    const settledMeasurement = window.setTimeout(updateRailState, 180);
    const resizeObserver = new ResizeObserver(updateRailState);
    resizeObserver.observe(rail);
    rail.querySelectorAll(".trailer-card").forEach((card) => {
      resizeObserver.observe(card);
    });
    window.addEventListener("resize", updateRailState);
    rail.addEventListener("scroll", updateRailState, { passive: true });

    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(settledMeasurement);
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateRailState);
      rail.removeEventListener("scroll", updateRailState);
    };
  }, [updateRailState, videos.length]);

  if (videos.length === 0 || (primaryVideo && videos.length === 1)) {
    return null;
  }

  function scrollRail(direction: -1 | 1) {
    const rail = railRef.current;
    if (!rail) {
      return;
    }

    const firstCard = rail.querySelector<HTMLElement>(".trailer-card");
    const cardWidth = firstCard?.getBoundingClientRect().width ?? rail.clientWidth;
    const gap = 16;
    const visibleCards = Math.max(1, Math.floor(rail.clientWidth / (cardWidth + gap)));
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    rail.scrollBy({
      left: direction * (cardWidth + gap) * visibleCards,
      behavior: reduceMotion ? "auto" : "smooth",
    });
  }

  return (
    <section className="trailer-section" aria-labelledby="trailers-heading">
      <div className="trailer-section__header">
        <div className="trailer-section__title">
          <span className="trailer-section__title-icon" aria-hidden="true">
            <span className="trailer-play-icon" />
          </span>
          <h2 id="trailers-heading">Trailers &amp; More</h2>
          <span className="trailer-section__count">
            {videos.length} video{videos.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="trailer-rail-controls" aria-label="Video rail controls">
          <button
            type="button"
            aria-label="Previous videos"
            disabled={!canScrollPrevious}
            onClick={() => scrollRail(-1)}
          >
            <span aria-hidden="true">←</span>
          </button>
          <button
            type="button"
            aria-label="Next videos"
            disabled={!canScrollNext}
            onClick={() => scrollRail(1)}
          >
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </div>

      <div
        className={`trailer-rail-shell${canScrollPrevious ? " can-scroll-previous" : ""}${canScrollNext ? " can-scroll-next" : ""}`}
      >
        <div ref={railRef} className="trailer-rail" tabIndex={0}>
          {videos.map((video) => (
            <VideoCard
              key={`${video.site}:${video.source_video_id}`}
              video={video}
              onOpen={openVideo}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

type VideoCardProps = {
  video: ContentVideo;
  onOpen: (video: ContentVideo, trigger: HTMLElement) => void;
};

function VideoCard({ video, onOpen }: VideoCardProps) {
  const [showThumbnail, setShowThumbnail] = useState(true);
  const thumbnailUrl = getSafeYouTubeThumbnailUrl(video);
  const language = getVideoLanguageLabel(video.language_code);
  const name = getVideoDisplayName(video);

  return (
    <button
      className="trailer-card"
      type="button"
      aria-label={`Play ${name}`}
      onClick={(event) => onOpen(video, event.currentTarget)}
    >
      <span className="trailer-card__visual">
        {showThumbnail && thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt=""
            loading="lazy"
            onError={() => setShowThumbnail(false)}
          />
        ) : (
          <span className="trailer-card__fallback" aria-hidden="true" />
        )}
        <span className="trailer-card__badges" aria-hidden="true">
          <span className="trailer-card__type">{getVideoTypeLabel(video)}</span>
          {video.official ? (
            <span className="trailer-card__official">✓ Official</span>
          ) : null}
        </span>
        <span className="trailer-card__play" aria-hidden="true">
          <span className="trailer-play-icon" />
        </span>
      </span>
      <span className="trailer-card__copy">
        <strong>{name}</strong>
        {language ? <span className="trailer-card__language">{language}</span> : null}
      </span>
    </button>
  );
}

type TrailerModalProps = {
  contentTitle: string;
  video: ContentVideo;
  onClose: () => void;
};

function TrailerModal({ contentTitle, video, onClose }: TrailerModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [playerLoaded, setPlayerLoaded] = useState(false);
  const embedUrl = getSafeEmbedUrl(video, true);
  const watchUrl = getSafeWatchUrl(video);
  const thumbnailUrl = getSafeYouTubeThumbnailUrl(video);
  const language = getVideoLanguageLabel(video.language_code);
  const name = getVideoDisplayName(video);

  useEffect(() => {
    setPlayerLoaded(false);
  }, [video.site, video.source_video_id]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || !embedUrl) {
      onClose();
      return;
    }

    const previousOverflow = document.body.style.overflow;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };

    dialog.showModal();
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleEscape);
    closeButtonRef.current?.focus();

    return () => {
      document.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = previousOverflow;
      if (dialog.open) {
        dialog.close();
      }
    };
  }, [embedUrl, onClose]);

  if (!embedUrl) {
    return null;
  }

  function handleBackdropClick(event: ReactMouseEvent<HTMLDialogElement>) {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="trailer-modal"
      aria-labelledby="trailer-modal-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={handleBackdropClick}
    >
      <div className="trailer-modal__panel">
        <div className="trailer-modal__header">
          <h2 id="trailer-modal-title">{name}</h2>
          <button
            ref={closeButtonRef}
            className="trailer-modal__close"
            type="button"
            aria-label="Close trailer"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <div className="trailer-modal__player">
          {!playerLoaded ? (
            <div className="trailer-modal__loading" role="status">
              {thumbnailUrl ? <img src={thumbnailUrl} alt="" aria-hidden="true" /> : null}
              <span className="trailer-modal__spinner" aria-hidden="true" />
              <span className="sr-only">Loading video</span>
            </div>
          ) : null}
          <iframe
            className={playerLoaded ? "is-loaded" : ""}
            src={embedUrl}
            title={`${name} for ${contentTitle}`}
            loading="lazy"
            allow="autoplay; encrypted-media; picture-in-picture"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
            onLoad={() => setPlayerLoaded(true)}
          />
        </div>

        <div className="trailer-modal__footer">
          <div className="trailer-modal__metadata">
            <span>{getVideoTypeLabel(video)}</span>
            {video.official ? <span>Official</span> : null}
            {language ? <span>{language}</span> : null}
          </div>
          {watchUrl ? (
            <a href={watchUrl} target="_blank" rel="noopener noreferrer">
              Open on YouTube <span aria-hidden="true">↗</span>
            </a>
          ) : null}
        </div>
      </div>
    </dialog>
  );
}
