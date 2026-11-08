// Mirrors tanami-backend/contracts/openapi.json (schemas used by staff screens).

export type Role = "farmer" | "expert" | "moderator" | "admin";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Me {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: Role;
  consent_training_data: boolean;
  created_at: string;
}

export interface Page<T> {
  data: T[];
  meta: { next_cursor: string | null; has_more: boolean };
}

export interface Overview {
  generated_at: string;
  timezone: string;
  users: { total: number; new_7d: number; pending_deletion: number; by_role: Record<Role, number> };
  tracking: {
    active_plants: number;
    ended_plants: number;
    outcomes: Record<"failed" | "suboptimal" | "normal" | "bumper", number>;
  };
  detection: { active_detection_plants: number; scans_total: number; scans_7d: number };
  queues: { open_reports: number; feedback_pending: number };
  scans_daily: { day: string; disease: number; ripeness: number }[];
  scan_status_30d: Record<string, number>;
  top_diseases_30d: { code: string; name: string; count: number }[];
}

export type PostStatus = "published" | "hidden" | "removed";
export type ReportAction = "dismiss" | "hide" | "remove";

export interface ReportedTarget {
  target_type: "post" | "comment";
  target_id: string;
  status: PostStatus;
  excerpt: string;
  author: { id: string; username: string; display_name: string; role: Role; is_expert: boolean };
  post_id: string;
  report_count: number;
  reasons: Record<string, number>;
  first_reported_at: string;
  last_reported_at: string;
}

export interface FeedbackItem {
  id: string;
  scan_id: string;
  scan_type: "disease" | "ripeness";
  image_url: string;
  model_version: string;
  predicted: Record<string, unknown> | null;
  value: "correct" | "incorrect";
  comment: string | null;
  correct_label: string | null;
  consent_training_data: boolean;
  allowed_labels: string[];
  reviewed_at: string | null;
  created_at: string;
}

export interface TreatmentStep {
  title: string;
  how: string;
}

export interface Treatments {
  first_aid: string[];
  organic: TreatmentStep[];
  chemical: TreatmentStep[];
  safety_note: string;
  when_to_call_expert: string;
}

export interface Disease {
  code: string;
  commodity_code: string;
  name_id: string;
  name_latin: string | null;
  cause_category: string;
  symptoms: string;
  causes_text: string;
  treatments: Partial<Treatments>;
  prevention: string;
  severity_note: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  is_active: boolean;
  updated_at: string;
}

export interface StaffUser {
  id: string;
  username: string;
  full_name: string;
  email: string;
  role: Role;
  consent_training_data: boolean;
  deleted_at: string | null;
  created_at: string;
}

export interface Broadcast {
  batch: string;
  title: string;
  body: string;
  audience: "all" | "user";
  recipients: number;
  read: number;
  sent_at: string;
}
