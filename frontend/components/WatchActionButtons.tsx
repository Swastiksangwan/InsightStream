"use client";

import { useState, useTransition } from "react";
import {
  addContentToWatchLater,
  markContentAsWatched,
  removeContentFromWatched,
  removeContentFromWatchLater,
} from "@/lib/watchActions";
import type { WatchStatus } from "@/types/content";

type WatchActionButtonsProps = {
  contentId: number;
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

function formatFeedbackMessage(message: string) {
  const normalizedMessage = message.toLowerCase();

  if (normalizedMessage.includes("already in watch later")) {
    return "Already in watch later";
  }

  if (normalizedMessage.includes("already in watched")) {
    return "Already watched";
  }

  if (normalizedMessage.includes("removed from watched")) {
    return "Removed from watched";
  }

  if (normalizedMessage.includes("removed from watch later")) {
    return "Removed from watch later";
  }

  if (normalizedMessage.includes("added to watched")) {
    return "Marked as watched";
  }

  if (normalizedMessage.includes("added to watch later")) {
    return "Added to watch later";
  }

  return message || "Something went wrong";
}

export function WatchActionButtons({
  contentId,
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
      const result =
        status === "watch_later"
          ? await removeContentFromWatchLater(contentId)
          : await addContentToWatchLater(contentId);

      if (result.ok) {
        setStatus(result.status);
        setFeedback({ type: "success", text: formatFeedbackMessage(result.message) });
        return;
      }

      setFeedback({ type: "error", text: formatFeedbackMessage(result.message) });
    });
  }

  function handleWatched() {
    setFeedback(null);

    startTransition(async () => {
      const result =
        status === "watched"
          ? await removeContentFromWatched(contentId)
          : await markContentAsWatched(contentId);

      if (result.ok) {
        setStatus(result.status);
        setFeedback({ type: "success", text: formatFeedbackMessage(result.message) });
        return;
      }

      setFeedback({ type: "error", text: formatFeedbackMessage(result.message) });
    });
  }

  const isWatchLater = status === "watch_later";
  const isWatched = status === "watched";
  const watchLaterLabel = isWatchLater
    ? "Remove from Watch Later"
    : "Add to Watch Later";
  const watchedLabel = isWatched ? "Remove from Watched" : "Mark as Watched";

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
          disabled={isPending || isWatched}
        >
          {watchLaterLabel}
        </button>

        <button
          type="button"
          className="watch-action-button watch-action-button--primary"
          onClick={handleWatched}
          disabled={isPending}
        >
          {watchedLabel}
        </button>
      </div>

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
