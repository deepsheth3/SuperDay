const getBaseUrl = () =>
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:5050";

export type TurnReference = { num: number; source_id: string; label: string };

export type Turn = {
  role: "user" | "assistant";
  message: string;
  list_items?: string[];
  references?: TurnReference[];
};

export type HistoryResponse = {
  turns: Turn[];
  session_id: string;
};

export type ChatResponse = {
  reply: string;
  session_id?: string;
  list_items?: string[];
  references?: TurnReference[];
  suggested_follow_ups?: string[];
  error?: string;
};

export async function getHistory(
  sessionId: string | null,
  tenantId?: string | null
): Promise<HistoryResponse> {
  const url = new URL(`${getBaseUrl()}/api/history`);
  if (sessionId) url.searchParams.set("session_id", sessionId);
  if (tenantId) url.searchParams.set("tenant_id", tenantId);
  const res = await fetch(url.toString(), { credentials: "include" });
  if (!res.ok) throw new Error("Failed to load history");
  return res.json();
}

export async function sendMessage(
  message: string,
  options?: {
    sessionId?: string | null;
    goal?: string | null;
    tenantId?: string | null;
  }
): Promise<ChatResponse> {
  const body: Record<string, string> = { message };
  if (options?.sessionId) body.session_id = options.sessionId;
  if (options?.goal) body.goal = options.goal;
  if (options?.tenantId) body.tenant_id = options.tenantId;
  const res = await fetch(`${getBaseUrl()}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  const data: ChatResponse = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}
