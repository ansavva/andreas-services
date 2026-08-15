import type { AssetResponse, ReelResponse, TextResponse, TreeResponse } from "../types";
import { apiGet } from "./client";

/** Immediate contents of one folder. */
export function getTree(prefix: string) {
  return apiGet<TreeResponse>("/api/tree", { prefix });
}

/** One page of images and videos beneath a prefix, recursively. */
export function getReel(prefix: string, cursor?: string) {
  return apiGet<ReelResponse>("/api/reel", { prefix, cursor });
}

/**
 * A fresh presigned URL for one object.
 *
 * Two callers: the download button (`attachment`, which is the only way a
 * cross-origin download actually downloads), and the media surfaces re-signing
 * a URL that expired while the tab sat idle.
 */
export function getAsset(key: string, disposition: "inline" | "attachment" = "inline") {
  return apiGet<AssetResponse>("/api/asset", { key, disposition });
}

/** A JSON/markdown/text object's contents, for the read-only viewer. */
export function getText(key: string) {
  return apiGet<TextResponse>("/api/text", { key });
}
