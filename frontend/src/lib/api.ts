const getBaseUrl = () =>
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

/** Bearer for Harper API when HARPER_JWT_JWKS_URL is set on the backend. */
export function buildAuthHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  const envTok = process.env.NEXT_PUBLIC_ACCESS_TOKEN;
  if (envTok) {
    h.Authorization = `Bearer ${envTok}`;
    return h;
  }
  if (typeof window !== "undefined") {
    const t = window.localStorage.getItem("harper_access_token");
    if (t) h.Authorization = `Bearer ${t}`;
  }
  return h;
}

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
  request_id?: string;
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
  const res = await fetch(url.toString(), {
    credentials: "include",
    headers: { ...buildAuthHeaders() },
  });
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
  const requestId =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const body: Record<string, string> = { message, request_id: requestId };
  if (options?.sessionId) body.session_id = options.sessionId;
  if (options?.goal) body.goal = options.goal;
  if (options?.tenantId) body.tenant_id = options.tenantId;
  const res = await fetch(`${getBaseUrl()}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(),
    },
    credentials: "include",
    body: JSON.stringify(body),
  });
  const data: ChatResponse = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}
