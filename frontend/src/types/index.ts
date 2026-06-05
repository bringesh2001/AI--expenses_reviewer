export type SubmissionStatus =
  | "draft"
  | "pending_review"
  | "reviewing"
  | "approved"
  | "rejected"
  | "needs_revision";

export type VerdictType = "compliant" | "flagged" | "needs_review" | "rejected";

export interface Employee {
  id: string;
  employee_id: string;
  name: string;
  email: string;
  grade: number;
  department: string;
  role_title: string;
}

export interface Citation {
  chunk_id: string;
  policy_id: string;
  section: string;
  text: string;
  score: number;
}

export interface LineItem {
  id: string;
  receipt_filename: string | null;
  category: string | null;
  vendor: string | null;
  transaction_date: string | null;
  amount: number | null;
  currency: string;
  verdict: VerdictType | null;
  effective_verdict: VerdictType | null;
  confidence: number | null;
  reasoning: string | null;
  citations: Citation[] | null;
  override_verdict: VerdictType | null;
  override_note: string | null;
}

export interface Submission {
  id: string;
  employee_id: string;
  trip_purpose: string;
  trip_destination: string;
  trip_start_date: string;
  trip_end_date: string;
  status: SubmissionStatus;
  total_amount: number | null;
  snapshot_grade: number;
  snapshot_department: string;
  reviewer_note: string | null;
  reviewed_at: string | null;
  created_at: string;
  line_items: LineItem[];
}

export interface QAResponse {
  id: string;
  question: string;
  answer: string | null;
  status: "in_scope" | "out_of_scope";
  citations: Citation[] | null;
  confidence: number | null;
}
