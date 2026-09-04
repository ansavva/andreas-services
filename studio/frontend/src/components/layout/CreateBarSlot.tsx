import { CreateBar } from "../create/CreateBar";

/**
 * Where the create bar goes: the flexible middle of `TopBar`, between the
 * menu button and the search. Kept as a named slot so the bar's own layout
 * can grow line by line without the top bar knowing how tall it is.
 */
export function CreateBarSlot({ className = "min-w-0 flex-1" }: { className?: string }) {
  return (
    <div className={className} data-create-bar-slot="">
      <CreateBar />
    </div>
  );
}
