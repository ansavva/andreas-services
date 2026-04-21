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
  email_subject: string;
  email_sender: string;
  created_at: string;
  source_email_date: string;
}

export type SortOrder = "date-asc" | "date-desc" | "name-asc";

export type Theme = "light" | "dark";
