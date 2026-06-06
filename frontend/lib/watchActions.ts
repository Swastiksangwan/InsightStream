"use server";

import { revalidatePath } from "next/cache";
import {
  addToWatchLater,
  addToWatched,
  getWatched,
  getWatchLater,
  removeFromWatchLater,
  removeFromWatched,
} from "@/lib/api";
import { DEMO_USER_ID } from "@/lib/constants";
import type { Content, WatchStatus } from "@/types/content";

function includesContent(items: Content[], contentId: number) {
  return items.some((item) => item.id === contentId);
}

async function refreshDemoWatchStatus(
  contentId: number,
  fallbackStatus: WatchStatus,
) {
  try {
    const [watchLaterItems, watchedItems] = await Promise.all([
      getWatchLater(DEMO_USER_ID),
      getWatched(DEMO_USER_ID),
    ]);

    if (includesContent(watchedItems, contentId)) {
      return "watched" as const;
    }

    if (includesContent(watchLaterItems, contentId)) {
      return "watch_later" as const;
    }

    return "none" as const;
  } catch {
    return fallbackStatus;
  }
}

function buildFailure(error: unknown) {
  return {
    ok: false as const,
    message:
      error instanceof Error
        ? error.message
        : "Unable to update watch status right now.",
  };
}

export async function addContentToWatchLater(contentId: number) {
  try {
    const response = await addToWatchLater(DEMO_USER_ID, contentId);
    const status = await refreshDemoWatchStatus(contentId, "watch_later");
    revalidatePath(`/content/${contentId}`);

    return {
      ok: true as const,
      message: response.message,
      status,
    };
  } catch (error) {
    return buildFailure(error);
  }
}

export async function markContentAsWatched(contentId: number) {
  try {
    const response = await addToWatched(DEMO_USER_ID, contentId);
    const status = await refreshDemoWatchStatus(contentId, "watched");
    revalidatePath(`/content/${contentId}`);

    return {
      ok: true as const,
      message: response.message,
      status,
    };
  } catch (error) {
    return buildFailure(error);
  }
}

export async function removeContentFromWatchLater(contentId: number) {
  try {
    const response = await removeFromWatchLater(DEMO_USER_ID, contentId);
    const status = await refreshDemoWatchStatus(contentId, "none");
    revalidatePath(`/content/${contentId}`);

    return {
      ok: true as const,
      message: response.message,
      status,
    };
  } catch (error) {
    return buildFailure(error);
  }
}

export async function removeContentFromWatched(contentId: number) {
  try {
    const response = await removeFromWatched(DEMO_USER_ID, contentId);
    const status = await refreshDemoWatchStatus(contentId, "none");
    revalidatePath(`/content/${contentId}`);

    return {
      ok: true as const,
      message: response.message,
      status,
    };
  } catch (error) {
    return buildFailure(error);
  }
}
