import { getAsset } from "../apis/studio";

/**
 * Fetch a node's bytes, as a save rather than a view.
 *
 * **`window.location.assign`, not `<a download>`.** The URL is presigned and
 * therefore cross-origin to this app, and the `download` attribute is ignored
 * on a cross-origin href — the browser navigates to the picture instead of
 * saving it. What makes it a save is server-side: `attachment` signs the URL
 * with `response-content-disposition`, and the navigation ends in a download
 * rather than in a page.
 *
 * Written once because three surfaces do it — the open file, a run's output
 * and a tile's menu — and the reason above is not something to rediscover in
 * each of them.
 */
export async function downloadNode(node: string): Promise<void> {
  const asset = await getAsset(node, "attachment");
  window.location.assign(asset.url);
}
