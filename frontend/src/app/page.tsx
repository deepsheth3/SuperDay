"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getHistory,
  sendMessage,
  type ChatResponse,
  type Turn,
  type TurnReference,
} from "@/lib/api";

const SAMPLE_QUERIES = [
  { label: "Evergreen status", query: "What is the status of Evergreen Public Services?" },
  { label: "Harborline Hotel", query: "Tell me about Harborline Hotel Group" },
  { label: "Accounts in CO", query: "Accounts in Colorado" },
  { label: "Skyline contact", query: "Who is the contact for Skyline Protective Services?" },
];

function MessageBubble({
  turn,
  isThinking,
}: {
  turn: Turn;
  isThinking?: boolean;
}) {
  const isUser = turn.role === "user";
  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} w-full max-w-[90%] ${isUser ? "ml-auto" : "mr-auto"}`}
    >
      <div
        className={`rounded-lg px-4 py-3 border max-w-full ${
          isUser
            ? "bg-white border-harper-border text-harper-text"
            : "bg-white border-harper-border text-harper-text whitespace-pre-wrap"
        }`}
      >
        {isUser ? (
          <p className="text-harper-text">{turn.message}</p>
        ) : (
          <div className="space-y-2">
            {isThinking ? (
              <p className="text-harper-text opacity-80">Thinking…</p>
            ) : (
              <>
                <div className="narrative text-harper-text">{turn.message}</div>
                {turn.list_items && turn.list_items.length > 0 && (
                  <div className="msg-list pl-5 mt-2">
                    {turn.list_items.some((item) => /^\d+\.\s/.test(item)) ? (
                      <ol className="list-decimal list-inside space-y-1 text-harper-text text-sm">
                        {turn.list_items.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ol>
                    ) : (
                      <ul className="list-disc list-inside space-y-1 text-harper-text text-sm">
                        {turn.list_items.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
                {turn.references && turn.references.length > 0 && (
                  <div className="references mt-3 pt-3 border-t border-harper-border text-sm text-harper-text opacity-85">
                    <h4 className="font-semibold text-harper-secondary text-xs mb-1">
                      References
                    </h4>
                    <div className="space-y-0.5">
                      {turn.references.map((r: TurnReference) => (
                        <div key={r.num} className="ref-item">
                          [{r.num}] {r.label || r.source_id}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [suggestedFollowUps, setSuggestedFollowUps] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    setError(null);
    try {
      const data = await getHistory(sessionId);
      setTurns(data.turns || []);
      if (data.session_id) setSessionId(data.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load history");
      setTurns([]);
    } finally {
      setLoadingHistory(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setError(null);
    setSuggestedFollowUps([]);
    setTurns((prev) => [...prev, { role: "user", message: text }]);
    setTurns((prev) => [...prev, { role: "assistant", message: "" }]);
    setLoading(true);
    try {
      const data: ChatResponse = await sendMessage(text, {
        sessionId,
        goal: null,
        tenantId: null,
      });
      setTurns((prev) => {
        const next = [...prev];
        const lastIdx = next.length - 1;
        if (lastIdx >= 0 && next[lastIdx].role === "assistant" && !next[lastIdx].message) {
          next[lastIdx] = {
            role: "assistant",
            message: data.reply || "",
            list_items: data.list_items,
            references: data.references,
          };
        }
        return next;
      });
      if (data.session_id) setSessionId(data.session_id);
      if (data.suggested_follow_ups?.length)
        setSuggestedFollowUps(data.suggested_follow_ups);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setTurns((prev) => {
        const next = [...prev];
        const lastIdx = next.length - 1;
        if (lastIdx >= 0 && next[lastIdx].role === "assistant" && !next[lastIdx].message)
          next[lastIdx] = {
            role: "assistant",
            message: `Error: ${e instanceof Error ? e.message : "Request failed"}`,
          };
        return next;
      });
    } finally {
      setLoading(false);
    }
  }, [input, loading, sessionId]);

  const handleSample = (query: string) => {
    setInput(query);
  };

  const handleSuggestedClick = (s: string) => {
    setInput(s);
  };

  return (
    <div className="flex flex-col min-h-screen">
      <header className="flex-shrink-0 py-4 px-5 border-b border-harper-border bg-harper-bg">
        <h1 className="text-xl font-semibold text-harper-accent">Harper Agent</h1>
        <p className="text-sm text-harper-text opacity-90 mt-0.5">
          Ask about accounts, status, or contacts. Answers are grounded in your memory indices.
        </p>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto py-4 px-5 max-w-3xl w-full mx-auto"
      >
        {loadingHistory ? (
          <p className="text-harper-text opacity-70">Loading…</p>
        ) : (
          <div className="flex flex-col gap-3">
            {turns.length === 0 && !error && (
              <p className="text-harper-text opacity-80 text-sm">
                Send a message or try a sample query below.
              </p>
            )}
            {error && (
              <div className="rounded-lg px-4 py-2 bg-red-50 border border-red-200 text-red-800 text-sm">
                {error}
              </div>
            )}
            {turns.map((turn, i) => (
              <MessageBubble
                key={i}
                turn={turn}
                isThinking={
                  loading && i === turns.length - 1 && turn.role === "assistant" && !turn.message
                }
              />
            ))}
          </div>
        )}
      </div>

      <div className="flex-shrink-0 py-4 px-5 border-t border-harper-border bg-harper-bg">
        <div className="max-w-3xl mx-auto flex gap-2 items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder="e.g. What is the status of Evergreen Public Services?"
            className="flex-1 px-4 py-2.5 border border-harper-border rounded-lg bg-white text-harper-text focus:outline-none focus:border-harper-secondary"
            disabled={loading}
          />
          <button
            type="button"
            onClick={() => handleSend()}
            disabled={loading || !input.trim()}
            className="px-4 py-2.5 bg-harper-accent text-white font-medium rounded-lg hover:bg-harper-accentHover disabled:opacity-60 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
        {suggestedFollowUps.length > 0 && (
          <div className="max-w-3xl mx-auto mt-2">
            <p className="text-xs text-harper-text opacity-80 mb-1">Suggestions:</p>
            <div className="flex flex-wrap gap-2">
              {suggestedFollowUps.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleSuggestedClick(s)}
                  className="text-xs px-3 py-1.5 border border-harper-secondary text-harper-secondary rounded-md hover:border-harper-accent hover:text-harper-accent hover:bg-harper-accent/10"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="max-w-3xl mx-auto mt-2">
          <p className="text-xs text-harper-text opacity-80 mb-1">Sample queries:</p>
          <div className="flex flex-wrap gap-2">
            {SAMPLE_QUERIES.map(({ label, query }) => (
              <button
                key={query}
                type="button"
                onClick={() => handleSample(query)}
                className="text-xs px-3 py-1.5 border border-harper-secondary text-harper-secondary rounded-md hover:border-harper-accent hover:text-harper-accent hover:bg-harper-accent/10"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
