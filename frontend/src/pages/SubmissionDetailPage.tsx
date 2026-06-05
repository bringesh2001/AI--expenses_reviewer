import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { api, AuditEntry } from "../lib/api";
import type { Submission, VerdictType, LineItem } from "../types";
import { format } from "date-fns";
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  HelpCircle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  History,
} from "lucide-react";

const VERDICT_META: Record<VerdictType, { label: string; cls: string; icon: React.ElementType }> = {
  compliant:    { label: "Compliant",    cls: "bg-green-50 text-green-700 border-green-200", icon: CheckCircle },
  flagged:      { label: "Flagged",      cls: "bg-yellow-50 text-yellow-700 border-yellow-200", icon: AlertTriangle },
  needs_review: { label: "Needs review", cls: "bg-blue-50 text-blue-700 border-blue-200", icon: HelpCircle },
  rejected:     { label: "Rejected",     cls: "bg-red-50 text-red-700 border-red-200", icon: XCircle },
};

const VERDICT_OPTIONS: VerdictType[] = ["compliant", "flagged", "needs_review", "rejected"];

export default function SubmissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [sub, setSub] = useState<Submission | null>(null);
  const [loading, setLoading] = useState(true);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [showAudit, setShowAudit] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const [actioning, setActioning] = useState(false);
  const [overrideItem, setOverrideItem] = useState<string | null>(null);
  const [overrideVerdict, setOverrideVerdict] = useState<VerdictType>("compliant");
  const [overrideNote, setOverrideNote] = useState("");

  const fetch = useCallback(() => {
    if (!id) return;
    api.getSubmission(id).then(setSub).catch(console.error).finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  useEffect(() => {
    if (!sub || sub.status !== "reviewing") return;
    const interval = setInterval(fetch, 4000);
    return () => clearInterval(interval);
  }, [sub?.status, fetch]);

  async function handleReview(action: "approve" | "reject" | "send_back") {
    if (!id) return;
    setActioning(true);
    try {
      const updated = await api.reviewSubmission(id, action, reviewNote || undefined);
      setSub(updated);
      setReviewNote("");
    } catch (err) {
      console.error(err);
    } finally {
      setActioning(false);
    }
  }

  async function handleOverride(itemId: string) {
    if (!id) return;
    try {
      const updated = await api.overrideVerdict(id, itemId, overrideVerdict, overrideNote || undefined);
      setSub(updated);
      setOverrideItem(null);
      setOverrideNote("");
    } catch (err) {
      console.error(err);
    }
  }

  async function loadAudit() {
    if (!id) return;
    const log = await api.getAuditLog(id);
    setAuditLog(log);
    setShowAudit(true);
  }

  if (loading) return <div className="p-8 text-gray-400">Loading…</div>;
  if (!sub) return <div className="p-8 text-red-500">Submission not found</div>;

  const locked = sub.status === "approved";
  const canReview = sub.status === "pending_review";

  return (
    <div className="p-8 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{sub.trip_destination}</h1>
          <p className="text-sm text-gray-500 mt-0.5">{sub.trip_purpose}</p>
          <p className="text-xs text-gray-400 mt-1">
            {format(new Date(sub.trip_start_date), "MMM d")} –{" "}
            {format(new Date(sub.trip_end_date), "MMM d, yyyy")} ·{" "}
            Grade {sub.snapshot_grade} · {sub.snapshot_department}
          </p>
        </div>
        <StatusBadge status={sub.status} />
      </div>

      {/* Reviewing spinner */}
      {sub.status === "reviewing" && (
        <div className="flex items-center gap-2 text-sm text-brand-600 bg-brand-50 rounded-lg px-4 py-3">
          <RefreshCw size={14} className="animate-spin" />
          AI pre-review in progress…
        </div>
      )}

      {/* Reviewer note */}
      {sub.reviewer_note && (
        <div className="bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 text-sm text-orange-800">
          <strong>Reviewer note:</strong> {sub.reviewer_note}
        </div>
      )}

      {/* Line items */}
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-gray-800">
          Line items ({sub.line_items.length})
        </h2>
        {sub.line_items.length === 0 ? (
          <p className="text-sm text-gray-400">No receipts yet</p>
        ) : (
          sub.line_items.map((item) => <LineItemCard
            key={item.id}
            item={item}
            locked={locked}
            isOverriding={overrideItem === item.id}
            overrideVerdict={overrideVerdict}
            overrideNote={overrideNote}
            onStartOverride={() => {
              setOverrideItem(item.id);
              setOverrideVerdict((item.effective_verdict ?? "compliant") as VerdictType);
            }}
            onCancelOverride={() => setOverrideItem(null)}
            onConfirmOverride={() => handleOverride(item.id)}
            setOverrideVerdict={setOverrideVerdict}
            setOverrideNote={setOverrideNote}
          />)
        )}
      </div>

      {/* Total */}
      {sub.total_amount != null && (
        <div className="flex justify-end">
          <div className="text-right">
            <p className="text-sm text-gray-500">Reimbursable total</p>
            <p className="text-xl font-bold text-gray-900">${sub.total_amount.toFixed(2)}</p>
          </div>
        </div>
      )}

      {/* Reviewer actions */}
      {canReview && !locked && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-gray-700">Reviewer decision</h3>
          <textarea
            value={reviewNote}
            onChange={(e) => setReviewNote(e.target.value)}
            placeholder="Optional note…"
            rows={2}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <div className="flex gap-2">
            <button
              onClick={() => handleReview("approve")}
              disabled={actioning}
              className="flex-1 bg-green-600 hover:bg-green-700 text-white text-sm font-medium py-2 rounded-lg transition-colors disabled:opacity-60"
            >
              Approve
            </button>
            <button
              onClick={() => handleReview("send_back")}
              disabled={actioning}
              className="flex-1 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium py-2 rounded-lg transition-colors disabled:opacity-60"
            >
              Send back
            </button>
            <button
              onClick={() => handleReview("reject")}
              disabled={actioning}
              className="flex-1 bg-red-600 hover:bg-red-700 text-white text-sm font-medium py-2 rounded-lg transition-colors disabled:opacity-60"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {/* Approved banner */}
      {locked && (
        <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
          <CheckCircle size={14} />
          This submission is approved and read-only.
        </div>
      )}

      {/* Audit log */}
      <div>
        <button
          onClick={showAudit ? () => setShowAudit(false) : loadAudit}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800"
        >
          <History size={14} />
          {showAudit ? "Hide" : "Show"} audit log
          {showAudit ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
        {showAudit && (
          <div className="mt-3 border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Action</th>
                  <th className="px-3 py-2 text-left font-medium">Actor</th>
                  <th className="px-3 py-2 text-left font-medium">Note</th>
                  <th className="px-3 py-2 text-left font-medium">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {auditLog.map((entry) => (
                  <tr key={entry.id} className="bg-white">
                    <td className="px-3 py-2 font-medium capitalize">{entry.action.replace("_", " ")}</td>
                    <td className="px-3 py-2 text-gray-500">{entry.actor_type}</td>
                    <td className="px-3 py-2 text-gray-500 max-w-[200px] truncate">{entry.note ?? "—"}</td>
                    <td className="px-3 py-2 text-gray-400">{format(new Date(entry.created_at), "MMM d HH:mm")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function LineItemCard({
  item,
  locked,
  isOverriding,
  overrideVerdict,
  overrideNote,
  onStartOverride,
  onCancelOverride,
  onConfirmOverride,
  setOverrideVerdict,
  setOverrideNote,
}: {
  item: LineItem;
  locked: boolean;
  isOverriding: boolean;
  overrideVerdict: VerdictType;
  overrideNote: string;
  onStartOverride: () => void;
  onCancelOverride: () => void;
  onConfirmOverride: () => void;
  setOverrideVerdict: (v: VerdictType) => void;
  setOverrideNote: (n: string) => void;
}) {
  const verdict = (item.effective_verdict ?? item.verdict) as VerdictType | null;
  const meta = verdict ? VERDICT_META[verdict] : null;
  const Icon = meta?.icon ?? HelpCircle;

  return (
    <div className={`rounded-xl border p-4 space-y-2 ${meta ? meta.cls : "border-gray-200 bg-white"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Icon size={15} />
            <span className="font-medium text-sm">
              {item.vendor ?? item.receipt_filename ?? "Receipt"}
            </span>
            {item.override_verdict && (
              <span className="text-xs bg-white/60 px-1.5 py-0.5 rounded font-medium">
                reviewer override
              </span>
            )}
          </div>
          <p className="text-xs mt-0.5 opacity-70">
            {item.category ?? "—"} ·{" "}
            {item.transaction_date ? format(new Date(item.transaction_date), "MMM d, yyyy") : "—"}
          </p>
        </div>
        <div className="text-right shrink-0">
          {item.amount != null && (
            <p className="text-sm font-semibold">
              ${item.amount.toFixed(2)} {item.currency}
            </p>
          )}
          {item.confidence != null && (
            <p className="text-xs opacity-60 mt-0.5">
              {Math.round(item.confidence * 100)}% confidence
            </p>
          )}
        </div>
      </div>

      {item.reasoning && (
        <p className="text-xs opacity-80 leading-relaxed">{item.reasoning}</p>
      )}

      {item.citations && item.citations.length > 0 && (
        <div className="space-y-1">
          {item.citations.map((c: any, i: number) => (
            <div key={i} className="bg-white/50 rounded px-2 py-1 text-xs">
              <span className="font-medium">{c.policy_id} {c.section}</span>
              <span className="opacity-70"> — {c.text?.slice(0, 120)}{(c.text?.length ?? 0) > 120 ? "…" : ""}</span>
            </div>
          ))}
        </div>
      )}

      {/* Override UI */}
      {!locked && !isOverriding && (
        <button
          onClick={onStartOverride}
          className="text-xs opacity-60 hover:opacity-100 underline"
        >
          Override verdict
        </button>
      )}
      {isOverriding && (
        <div className="pt-2 space-y-2 border-t border-current/20">
          <select
            value={overrideVerdict}
            onChange={(e) => setOverrideVerdict(e.target.value as VerdictType)}
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs bg-white text-gray-800 focus:outline-none"
          >
            {["compliant", "flagged", "needs_review", "rejected"].map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
          <input
            value={overrideNote}
            onChange={(e) => setOverrideNote(e.target.value)}
            placeholder="Reason (optional)"
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs bg-white text-gray-800 focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              onClick={onConfirmOverride}
              className="flex-1 bg-gray-800 text-white text-xs py-1.5 rounded-lg"
            >
              Confirm
            </button>
            <button
              onClick={onCancelOverride}
              className="flex-1 bg-white border border-gray-300 text-gray-600 text-xs py-1.5 rounded-lg"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    draft: "bg-gray-100 text-gray-600",
    pending_review: "bg-yellow-100 text-yellow-700",
    reviewing: "bg-blue-100 text-blue-700",
    approved: "bg-green-100 text-green-700",
    rejected: "bg-red-100 text-red-700",
    needs_revision: "bg-orange-100 text-orange-700",
  };
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-medium capitalize ${styles[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
