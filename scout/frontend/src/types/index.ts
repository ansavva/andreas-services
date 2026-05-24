export interface Event {
  event_id: string;
  email_id: string;
  event_name: string;
  date: string;
  time: string;
  venue: string;
  price: string;
  description: string;
  links: string[];
  image_url: string;
  email_subject: string;
  email_sender: string;
  source_email_date: string;
  status: string;
  regions: string[];
  categories: string[];
  sender_key?: string;
}

export interface Region {
  slug: string;
  name: string;
  count: number;
}

export interface Category {
  slug: string;
  name: string;
  status?: string;
  count?: number;
  suggested_count?: number;
}

export interface Sender {
  sender_key: string;
  display_sender: string;
  regions: string[];
  status: string;
  first_seen?: string;
}

export interface ProcessedEmail {
  email_id: string;
  email_subject: string;
  email_sender: string;
  source_email_date: string;
  image_url: string;
  processed_at: string;
  event_count: number;
}

export type SortOrder = "date-asc" | "date-desc" | "name-asc";

export type Theme = "light" | "dark";
