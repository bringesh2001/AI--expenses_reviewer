import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { Submission, SubmissionStatus } from "../types";
import { format } from "date-fns";

const STATUS_STYLES: Record<SubmissionStatus, string> = {
  draft: "bg-gray-100 text-gray-600",
  pending_review: "bg-yellow-100 text-yellow-700",
  reviewing: "bg-blue-100 text-blue-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
  needs_revision: "bg-orange-100 text-orange-700",
};

const FILTERS: SubmissionStatus[] = [
  "reviewing",
  "needs_revision",
  "approved",
  "rejected",
];

export default function DashboardPage() {
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .listSubmissions(statusFilter ? { status_filter: statusFilter } : undefined)
      .then(setSubmissions)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [statusFilter]);

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Submissions</h1>
        <Link
          to="/submit/new"
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Submission
        </Link>
      </div>

      {/* Filter pills */}
      <div className="flex gap-2 mb-5 flex-wrap">
        <button
          onClick={() => setStatusFilter("")}
          className={`px-3 py-1 rounded-full text-sm border transition-colors ${
            !statusFilter ? "border-brand-500 text-brand-700 bg-brand-50" : "border-gray-300 text-gray-600"
          }`}
        >
          All
        </button>
        {FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-sm border capitalize transition-colors ${
              statusFilter === s
                ? "border-brand-500 text-brand-700 bg-brand-50"
                : "border-gray-300 text-gray-600"
            }`}
          >
            {s.replace("_", " ")}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-gray-400 text-sm">Loading…</p>
      ) : submissions.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <p className="text-lg">No submissions yet</p>
          <p className="text-sm mt-1">Create your first expense report</p>
        </div>
      ) : (
        <div className="space-y-3">
          {submissions.map((sub) => (
            <Link
              key={sub.id}
              to={`/submissions/${sub.id}`}
              className="block bg-white rounded-xl border border-gray-200 p-5 hover:border-brand-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium text-gray-900">{sub.trip_destination}</p>
                  <p className="text-sm text-gray-500 mt-0.5">{sub.trip_purpose}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {format(new Date(sub.trip_start_date), "MMM d")} –{" "}
                    {format(new Date(sub.trip_end_date), "MMM d, yyyy")}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_STYLES[sub.status]}`}>
                    {sub.status.replace("_", " ")}
                  </span>
                  {sub.total_amount != null && (
                    <p className="text-sm font-medium text-gray-700 mt-1">
                      ${sub.total_amount.toFixed(2)}
                    </p>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
