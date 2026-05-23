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
