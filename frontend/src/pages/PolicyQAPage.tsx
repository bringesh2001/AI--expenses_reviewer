import { useState, useRef, useEffect, FormEvent } from "react";
import { api } from "../lib/api";
import type { QAResponse } from "../types";
import { Send, BookOpen } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  text: string;
  response?: QAResponse;
}

export default function PolicyQAPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question) return;

    setMessages((p) => [...p, { role: "user", text: question }]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.askQuestion(question);
      setMessages((p) => [
        ...p,
        {
          role: "assistant",
          text: res.answer ?? "I cannot answer questions outside the scope of Northwind travel policy.",
          response: res,
        },
      ]);
    } catch (err: any) {
      setMessages((p) => [
        ...p,
        { role: "assistant", text: "Policy Q&A is not yet available." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="px-8 py-5 border-b border-gray-200 bg-white flex items-center gap-3">
        <BookOpen size={18} className="text-brand-600" />
        <h1 className="text-lg font-semibold text-gray-900">Policy Q&A</h1>
        <span className="text-xs text-gray-400">Ask about Northwind travel & expense policies</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-5">
        {messages.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <BookOpen size={28} className="mx-auto mb-3 opacity-40" />
            <p className="text-sm">Ask anything about the travel &amp; expense policy</p>
            <div className="mt-4 flex flex-col items-center gap-2">
              {SAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="text-xs text-brand-600 hover:underline"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-xl rounded-2xl px-4 py-3 text-sm ${
              msg.role === "user"
                ? "bg-brand-600 text-white"
                : msg.response?.status === "out_of_scope"
                ? "bg-orange-50 border border-orange-200 text-orange-800"
                : "bg-white border border-gray-200 text-gray-800"
            }`}>
              <p className="leading-relaxed">{msg.text}</p>
              {msg.response?.citations && msg.response.citations.length > 0 && (
                <div className="mt-3 space-y-1.5 border-t border-gray-100 pt-2">
                  {msg.response.citations.map((c, j) => (
                    <div key={j} className="text-xs text-gray-500">
                      <span className="font-medium">{c.policy_id} {c.section}</span>
                      <span> — {c.text.slice(0, 120)}{c.text.length > 120 ? "…" : ""}</span>
                    </div>
                  ))}
                </div>
              )}
              {msg.response?.confidence != null && (
                <p className="mt-2 text-xs opacity-50">
                  Confidence {Math.round(msg.response.confidence * 100)}%
                </p>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3 text-sm text-gray-400 animate-pulse">
              Searching policies…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="px-8 py-5 border-t border-gray-200 bg-white flex gap-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="What is the lodging limit for Chicago?"
          className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-xl transition-colors disabled:opacity-50"
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  );
}

const SAMPLE_QUESTIONS = [
  "What is the hotel limit for Chicago?",
  "Can I fly business class on a 4-hour domestic flight?",
  "Is alcohol reimbursable?",
  "What receipts do I need to submit?",
];
