"use server";

import { revalidatePath } from "next/cache";
import {
  addToWatchLater,
  addToWatched,
  removeFromWatchLater,
  removeFromWatched,
} from "@/lib/api";
import { DEMO_USER_ID } from "@/lib/constants";

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
    revalidatePath(`/content/${contentId}`);

    return {
      ok: true as const,
      message: response.message,
      status: "watch_later" as const,
    };
  } catch (error) {
    return buildFailure(error);
  }
}

export async function markContentAsWatched(contentId: number) {
  try {
    const response = await addToWatched(DEMO_USER_ID, contentId);
    revalidatePath(`/content/${contentId}`);

    return {
      ok: true as const,
      message: `${response.message}. Removed from Watch Later if it was there.`,
      status: "watched" as const,
    };
  } catch (error) {
    return buildFailure(error);
  }
}

export async function removeContentFromWatchLater(contentId: number) {
  try {
    const response = await removeFromWatchLater(DEMO_USER_ID, contentId);
    revalidatePath(`/content/${contentId}`);

    return {
      ok: true as const,
      message: response.message,
      status: "none" as const,
    };
  } catch (error) {
    return buildFailure(error);
  }
}

export async function removeContentFromWatched(contentId: number) {
  try {
    const response = await removeFromWatched(DEMO_USER_ID, contentId);
    revalidatePath(`/content/${contentId}`);

    return {
      ok: true as const,
      message: response.message,
      status: "none" as const,
    };
  } catch (error) {
    return buildFailure(error);
  }
}
