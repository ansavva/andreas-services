/**
 * Where the create bar goes. Filled by the create bar (slice 3); until then it
 * renders only the space the bar will take, so the search already sits where
 * it will.
 */
export function CreateBarSlot({ className = "min-w-0 flex-1" }: { className?: string }) {
  return <div className={className} data-create-bar-slot="" />;
}
