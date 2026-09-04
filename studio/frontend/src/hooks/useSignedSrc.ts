import { useCallback, useEffect, useState } from "react";

import { getAsset } from "../apis/studio";

/**
 * A presigned URL that heals itself when S3 stops honouring it.
 *
 * Presigned URLs are short-lived by design — a URL signed with the Lambda
 * role's temporary credentials dies with them regardless of the expiry we ask
 * for — so a tab left open on a folder will eventually have a grid of broken
 * images. Rather than polling or guessing a TTL, every media element reports
 * its own `onError` here and we re-sign exactly the ones that failed.
 *
 * `attempted` caps this at one retry per node so a genuinely missing object
 * (deleted upstream between the listing and the render) cannot loop.
 *
 * **Takes the node id, not a name path.** `/api/asset?key=` signs a raw S3
 * key, and anything uploaded through the app has its bytes at `blobs/<id>` —
 * a name path handed there could never be re-signed, and every expired tile
 * would stay broken.
 */
export function useSignedSrc(nodeId: string, initialUrl: string) {
  const [src, setSrc] = useState(initialUrl);
  const [attempted, setAttempted] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setSrc(initialUrl);
    setAttempted(false);
    setFailed(false);
  }, [initialUrl, nodeId]);

  const onError = useCallback(() => {
    if (attempted) {
      setFailed(true);
      return;
    }
    setAttempted(true);
    getAsset(nodeId)
      .then((asset) => setSrc(asset.url))
      .catch(() => setFailed(true));
  }, [attempted, nodeId]);

  return { src, failed, onError };
}
