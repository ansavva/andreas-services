// Domain types for the Scout admin console and public UI.

// --- Public ---------------------------------------------------------------

export interface LabelRef {
  id: string;
  name: string;
}

export interface PublicLocation {
  name: string;
  address: string;
}

export interface PublicImage {
  // Absolute URL on our own API domain (or external source URL for legacy
  // url-only images); always usable as an `<img src>` directly.
  url: string;
}

export interface PublicSubEvent {
  subevent_id: string;
  start_date: string;
  start_time?: string | null;
  end_time?: string | null;
  location: PublicLocation | null;
  event_labels: LabelRef[];
  location_labels: LabelRef[];
  images: PublicImage[];
}

export interface PublicEvent {
  event_id: string;
  title: string;
  description: string;
  start_date: string;
  start_time?: string | null;
  end_time?: string | null;
  location: PublicLocation | null;
  event_labels: LabelRef[];
  location_labels: LabelRef[];
  images: PublicImage[];
  sub_events: PublicSubEvent[];
  no_upcoming_dates?: boolean;
}

export interface Feed {
  events: PublicEvent[];
  next_cursor: string | null;
  total: number;
}

export interface FacetLocation {
  id: string;
  name: string;
  address: string;
}

export interface Facets {
  locations: FacetLocation[];
  event_labels: LabelRef[];
  location_labels: LabelRef[];
}

export interface PublicFilters {
  location_id?: string;
  event_labels: string[];
  location_labels: string[];
  q?: string;
}

// --- Admin ----------------------------------------------------------------

export type LabelTaxonomy = "source" | "event" | "location";

export interface Label {
  label_id: string;
  name: string;
  name_norm?: string;
}

export interface Location {
  location_id: string;
  name: string;
  address: string;
  timezone: string;
}

export type SourceType = "email" | "webpage";

export interface Source {
  source_id: string;
  type: SourceType;
  identity: string;
  name: string;
  status: "active" | "disabled";
  archived: boolean;
  follow_links: boolean;
  config: Record<string, string>;
  next_run_at?: string;
  last_run_at?: string;
  last_run_status?: string;
  consecutive_zero_event_runs?: number;
  agent_model_override?: string | null;
  running?: boolean;
}

export interface LinkOutcome {
  url: string;
  ok: boolean;
  status?: number;
  reason?: string;
  s3_ref?: string;
}

export interface RunSummary {
  created?: number;
  skipped?: number;
  pages?: number;
  event_ids?: string[];
}

export interface ArtifactDescriptor {
  kind: string;
  label: string;
  index?: number;
  // Absolute our-domain URL for fetching the artifact in chunks.
  url: string;
}

export interface SourceRun {
  run_id: string;
  source_id: string;
  trigger: string;
  status: string;
  started_at: string;
  finished_at?: string;
  error_reason?: string;
  events_count?: number;
  link_outcomes?: LinkOutcome[];
  extracted_summary?: RunSummary;
  artifacts?: ArtifactDescriptor[];
}

export interface ArtifactChunk {
  kind: string;
  content: string;
  offset: number;
  next_offset: number | null;
  total: number;
}

// Paginated admin list response: items + opaque cursor for the next page.
export interface CursorPage<T> {
  next_cursor: string | null;
  items: T[];
}

// One entry in an event's append-only review trail. Internal admin record —
// never surfaced on the public/preview shapes.
export interface ReviewFeedback {
  at: string;
  decision: string;
  text: string;
  author?: string;
}

export interface AdminEvent {
  PK?: string;
  SK?: string;
  entity_type?: string;
  event_id: string;
  subevent_id?: string;
  parent_event_id?: string;
  source_id?: string;
  title?: string;
  description_md?: string;
  start_date?: string;
  start_time?: string | null;
  end_time?: string | null;
  location_id?: string | null;
  review_status?: string;
  publish_status?: string;
  lifecycle_cancelled?: boolean;
  past?: boolean;
  edited?: boolean;
  review_feedback?: ReviewFeedback[];
}

export interface SubEvent {
  subevent_id: string;
  parent_event_id: string;
  SK?: string;
  start_date: string;
  start_time?: string | null;
  end_time?: string | null;
  review_status: string;
  publish_status: string;
  lifecycle_cancelled?: boolean;
}

// Parent-centric review-queue entry: a parent event with all its occurrences.
// `parent_matches` is false when the parent surfaces only because an occurrence
// matches the current tab — it's then shown as a muted, non-actionable container.
export interface ReviewGroup {
  event: AdminEvent;
  parent_matches: boolean;
  subevents: SubEvent[];
}

export type Settings = Record<string, string | number>;

export interface Notification {
  notification_id: string;
  type: string;
  message: string;
  severity: string;
  read: boolean;
  source_id?: string;
  run_id?: string;
}

export interface DeletedItem {
  PK: string;
  SK: string;
  entity_type?: string;
  name?: string;
  title?: string;
  identity?: string;
}
