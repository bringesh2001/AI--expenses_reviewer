import axios from "axios";
import type { Employee, Submission, QAResponse } from "../types";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const client = axios.create({ baseURL: BASE });

export const api = {
  // Employees
  getEmployee: (id: string) =>
    client.get<Employee>(`/employees/${id}`).then((r) => r.data),
  listEmployees: () =>
    client.get<Employee[]>("/employees/").then((r) => r.data),

  // Submissions
  createSubmission: (body: {
    employee_id: string;
    trip_purpose: string;
    trip_destination: string;
    trip_start_date: string;
    trip_end_date: string;
  }) => client.post<Submission>("/submissions/", body).then((r) => r.data),

  uploadReceipt: (submissionId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return client
      .post<{ line_item_id: string; status: string }>(
        `/submissions/${submissionId}/receipts`,
        form
      )
      .then((r) => r.data);
  },

  submitForReview: (submissionId: string) =>
    client
      .post<Submission>(`/submissions/${submissionId}/submit`)
      .then((r) => r.data),

  getSubmission: (id: string) =>
    client.get<Submission>(`/submissions/${id}`).then((r) => r.data),

  listSubmissions: (params?: {
    employee_id?: string;
    status_filter?: string;
  }) => client.get<Submission[]>("/submissions/", { params }).then((r) => r.data),

  reviewSubmission: (id: string, action: "approve" | "reject" | "send_back", note?: string) =>
    client
      .post<Submission>(`/submissions/${id}/review`, { action, note })
      .then((r) => r.data),

  overrideVerdict: (submissionId: string, itemId: string, verdict: string, note?: string) =>
    client
      .post<Submission>(`/submissions/${submissionId}/items/${itemId}/override`, { verdict, note })
      .then((r) => r.data),

  getAuditLog: (submissionId: string) =>
    client.get<AuditEntry[]>(`/submissions/${submissionId}/audit`).then((r) => r.data),

  // Q&A
  askQuestion: (question: string) =>
    client.post<QAResponse>("/qa/", { question }).then((r) => r.data),
};

export interface AuditEntry {
  id: string;
  action: string;
  actor_type: string;
  actor_id: string | null;
  note: string | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  created_at: string;
}
