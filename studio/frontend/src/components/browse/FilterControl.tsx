import { Input } from "@ansavva/design-system";

import type { FileEntry, FolderEntry } from "../../types";

interface Props {
  value: string;
  onChange: (next: string) => void;
  /** How many the filter is currently hiding, for the placeholder. */
  total: number;
}

/**
 * Narrow what a folder is showing, by name, tag or caption.
 *
 * **A folder of three hundred outputs had a sort and no filter**, so finding one
 * frame meant scrolling. The captions and tags that #483 added were worse than
 * unused — nothing could search them, so writing one bought nothing back.
 *
 * It filters what is already loaded rather than asking the API. A listing is one
 * request and already in hand; a query per keystroke would be a request per
 * keystroke for a set the client is holding. The consequence to know is that it
 * narrows *this folder*, not the library — which is what a filter beside a
 * folder's own heading should mean.
 */
export function FilterControl({ value, onChange, total }: Props) {
  return (
    <div className="min-w-40 flex-1 sm:max-w-64">
      <Input
        value={value}
        onValueChange={onChange}
        aria-label="Filter this folder"
        placeholder={`Filter ${total} item${total === 1 ? "" : "s"}…`}
      />
    </div>
  );
}

/**
 * Does this entry match what was typed?
 *
 * Name, tags and description — the three things a person would think of as
 * "what this is". Case-folded, and a space-separated query has to match all of
 * its terms, so `pool whistle` narrows rather than widening.
 *
 * The **key is deliberately not searched.** It is a name path, so every entry in
 * a folder shares most of it and typing a folder's own name would match all of
 * them — a filter that matches everything is a filter that does nothing.
 */
export function matchesFilter(entry: FileEntry, query: string): boolean {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;

  const haystack = [entry.name, entry.description ?? "", ...(entry.tags ?? [])]
    .join(" ")
    .toLowerCase();
  return terms.every((term) => haystack.includes(term));
}

/** Folders match on their name alone — they carry no caption and no tags. */
export function folderMatchesFilter(folder: FolderEntry, query: string): boolean {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  return terms.every((term) => folder.name.toLowerCase().includes(term));
}
