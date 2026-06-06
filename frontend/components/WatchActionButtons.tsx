"use client";

import { useState, useTransition } from "react";
import {
  addContentToWatchLater,
  markContentAsWatched,
} from "@/lib/watchActions";
import type { WatchStatus } from "@/types/content";

type WatchActionButtonsProps = {
  contentId: number;
  title?: string;
  initialStatus?: WatchStatus;
  initialMessage?: string;
};

type Feedback = {
  type: "success" | "error" | "info";
  text: string;
};

function getStatusLabel(status: WatchStatus) {
  if (status === "watched") {
    return "Watched";
  }

  if (status === "watch_later") {
    return "In Watch Later";
  }

  return "Not saved yet";
}

export function WatchActionButtons({
  contentId,
  title,
  initialStatus = "none",
  initialMessage,
}: WatchActionButtonsProps) {
  const [status, setStatus] = useState<WatchStatus>(initialStatus);
  const [feedback, setFeedback] = useState<Feedback | null>(
    initialMessage ? { type: "info", text: initialMessage } : null,
  );
  const [isPending, startTransition] = useTransition();

  function handleWatchLater() {
    setFeedback(null);

    startTransition(async () => {
      const result = await addContentToWatchLater(contentId);

      if (result.ok) {
        setStatus(result.status);
        setFeedback({ type: "success", text: result.message });
        return;
      }

      setFeedback({ type: "error", text: result.message });
    });
  }

  function handleWatched() {
    setFeedback(null);

    startTransition(async () => {
      const result = await markContentAsWatched(contentId);

      if (result.ok) {
        setStatus(result.status);
        setFeedback({ type: "success", text: result.message });
        return;
      }

      setFeedback({ type: "error", text: result.message });
    });
  }

  const isWatchLater = status === "watch_later";
  const isWatched = status === "watched";

  return (
    <section className="detail-panel watch-actions" aria-label="Personal watch actions">
      <div className="detail-panel__header">
        <span className="section-label">Personal action</span>
        <h2>Watch Status</h2>
      </div>

      <div className="watch-actions__status">
        <span>Status</span>
        <strong>{getStatusLabel(status)}</strong>
      </div>

      <div className="watch-actions__buttons">
        <button
          type="button"
          className="watch-action-button watch-action-button--secondary"
          onClick={handleWatchLater}
          disabled={isPending || isWatchLater || isWatched}
        >
          {isWatchLater ? "In Watch Later" : "Add to Watch Later"}
        </button>

        <button
          type="button"
          className="watch-action-button watch-action-button--primary"
          onClick={handleWatched}
          disabled={isPending || isWatched}
        >
          {isWatched ? "Watched" : "Mark as Watched"}
        </button>
      </div>

      <p className="watch-actions__hint">
        Marking{title ? ` ${title}` : " this title"} as watched removes it from
        Watch Later if needed.
      </p>

      {isPending ? (
        <p className="watch-actions__message watch-actions__message--info" role="status">
          Updating watch status...
        </p>
      ) : null}

      {feedback ? (
        <p
          className={`watch-actions__message watch-actions__message--${feedback.type}`}
          role={feedback.type === "error" ? "alert" : "status"}
        >
          {feedback.text}
        </p>
      ) : null}
    </section>
  );
}
