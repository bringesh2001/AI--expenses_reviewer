import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Upload, X, ChevronRight } from "lucide-react";

type Step = 1 | 2;

interface TripInfo {
  employee_id: string;
  trip_purpose: string;
  trip_destination: string;
  trip_start_date: string;
  trip_end_date: string;
}

export default function NewSubmissionPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>(1);
  const [tripInfo, setTripInfo] = useState<TripInfo>({
    employee_id: "",
    trip_purpose: "",
    trip_destination: "",
    trip_start_date: "",
    trip_end_date: "",
  });
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleStep1(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const sub = await api.createSubmission(tripInfo);
      setSubmissionId(sub.id);
      setStep(2);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message);
    }
  }

  function handleFileDrop(e: React.DragEvent) {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files);
    setFiles((prev) => [...prev, ...dropped]);
  }

  const [uploadedFiles, setUploadedFiles] = useState<Set<string>>(new Set());

  async function handleSubmitForReview() {
    if (!submissionId) return;
    setSubmitting(true);
    setError(null);
    try {
      // Upload only files not yet uploaded
      const notYetUploaded = files.filter((f) => !uploadedFiles.has(f.name + f.size));
      if (notYetUploaded.length > 0) {
        setUploading(true);
        for (const f of notYetUploaded) {
          await api.uploadReceipt(submissionId, f);
          setUploadedFiles((prev) => new Set(prev).add(f.name + f.size));
        }
        setUploading(false);
      }

      await api.submitForReview(submissionId);
      navigate(`/submissions/${submissionId}`);
    } catch (err: any) {
      const detail: string = err.response?.data?.detail ?? err.message ?? "";
      // If already submitted (e.g. double-click), just navigate to the detail page
      if (err.response?.status === 409 && detail.includes("pending_review")) {
        navigate(`/submissions/${submissionId}`);
        return;
      }
      setError(detail);
      setSubmitting(false);
      setUploading(false);
    }
  }

  return (
    <div className="p-8 max-w-2xl mx-auto">
      {/* Step indicator */}
      <div className="flex items-center gap-3 mb-8">
        <StepDot n={1} active={step === 1} done={step > 1} label="Trip details" />
        <div className="flex-1 h-px bg-gray-200" />
        <StepDot n={2} active={step === 2} done={false} label="Upload receipts" />
      </div>

      {step === 1 && (
        <form onSubmit={handleStep1} className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">Trip details</h2>

          <Field label="Employee ID">
            <input
              required
              value={tripInfo.employee_id}
              onChange={(e) => setTripInfo((p) => ({ ...p, employee_id: e.target.value }))}
              className={inputCls}
              placeholder="NW-05117"
            />
          </Field>
          <Field label="Trip purpose">
            <input
              required
              value={tripInfo.trip_purpose}
              onChange={(e) => setTripInfo((p) => ({ ...p, trip_purpose: e.target.value }))}
              className={inputCls}
              placeholder="Chicago vendor site visit"
            />
          </Field>
          <Field label="Destination">
            <input
              required
              value={tripInfo.trip_destination}
              onChange={(e) => setTripInfo((p) => ({ ...p, trip_destination: e.target.value }))}
              className={inputCls}
              placeholder="Chicago, IL"
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Start date">
              <input
                type="date"
                required
                value={tripInfo.trip_start_date}
                onChange={(e) => setTripInfo((p) => ({ ...p, trip_start_date: e.target.value }))}
                className={inputCls}
              />
            </Field>
            <Field label="End date">
              <input
                type="date"
                required
                value={tripInfo.trip_end_date}
                onChange={(e) => setTripInfo((p) => ({ ...p, trip_end_date: e.target.value }))}
                className={inputCls}
              />
            </Field>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button type="submit" className="flex items-center gap-1 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-5 py-2 rounded-lg transition-colors">
            Next <ChevronRight size={14} />
          </button>
        </form>
      )}

      {step === 2 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <h2 className="text-lg font-semibold text-gray-900">Upload receipts</h2>
          <p className="text-sm text-gray-500">PDF, PNG, or JPEG. Each file = one receipt.</p>

          {/* Drop zone */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleFileDrop}
            onClick={() => fileRef.current?.click()}
            className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center cursor-pointer hover:border-brand-400 transition-colors"
          >
            <Upload size={24} className="mx-auto text-gray-400 mb-2" />
            <p className="text-sm text-gray-500">Drag & drop or <span className="text-brand-600 font-medium">browse</span></p>
          </div>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg"
            className="hidden"
            onChange={(e) => setFiles((p) => [...p, ...Array.from(e.target.files ?? [])])}
          />

          {/* File list */}
          {files.length > 0 && (
            <ul className="space-y-2">
              {files.map((f, i) => (
                <li key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 text-sm">
                  <span className="text-gray-700 truncate">{f.name}</span>
                  <button
                    onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}
                    className="text-gray-400 hover:text-red-500 ml-2 shrink-0"
                  >
                    <X size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex gap-3">
            <button
              onClick={() => setStep(1)}
              className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50"
            >
              Back
            </button>
            <button
              onClick={handleSubmitForReview}
              disabled={files.length === 0 || submitting}
              className="flex-1 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium py-2 rounded-lg transition-colors disabled:opacity-60"
            >
              {uploading ? "Uploading…" : submitting ? "Submitting…" : "Submit for review"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const inputCls =
  "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      {children}
    </div>
  );
}

function StepDot({ n, active, done, label }: { n: number; active: boolean; done: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
          active ? "bg-brand-600 text-white" : done ? "bg-brand-100 text-brand-700" : "bg-gray-100 text-gray-400"
        }`}
      >
        {n}
      </div>
      <span className={`text-sm font-medium ${active ? "text-brand-700" : "text-gray-400"}`}>{label}</span>
    </div>
  );
}
