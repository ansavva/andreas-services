import { getAsset, resolvePath } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { MediaThumb } from "../media/MediaThumb";

/**
 * The generic figure that says what an angle IS.
 *
 * An angle id reads `face_three_quarter_back_right` and its prompt spends a
 * paragraph defining that in terms of what is visible in frame; the picture says
 * it at a glance. These are the plates a face angle stopped SENDING when the
 * guide was found to distort the face it existed to record — which is exactly
 * why showing them is free: an illustration outside the payload cannot influence
 * a render.
 *
 * **Shared, because both screens that name an angle want it.** It lived inside
 * the Shoot tab's card, so the reference spec editor — where an angle's words
 * are actually written — showed the id and nothing else.
 *
 * Two calls rather than one: `/api/resolve` answers with a node VIEW and carries
 * no presigned url, so the url is asked for separately. Typed as a listing entry
 * it compiled, then threw on first render against the live API.
 */
export function AnglePlate({
  path,
  name,
  className = "w-20 shrink-0",
}: {
  path?: string | null;
  name: string;
  className?: string;
}) {
  const plate = useResource(
    path ? ["plate", path] : null,
    path
      ? async () => {
          const node = await resolvePath(path);
          return { id: node.id, url: (await getAsset(node.id)).url };
        }
      : null,
  );

  if (!plate.data) return null;
  return (
    <span className={className}>
      <MediaThumb
        nodeId={plate.data.id}
        url={plate.data.url}
        name={name}
        aspect="square"
        fit="contain"
      />
    </span>
  );
}
