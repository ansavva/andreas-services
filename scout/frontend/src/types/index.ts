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
  url?: string | null;
  s3_ref?: string | null;
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
