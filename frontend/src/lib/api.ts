export type AuthKind = "oauth_redirect" | "credentials_form" | "api_key_only";

export interface BrokerInfo {
  name: string;
  display_name: string;
  auth_kind: AuthKind;
  configured: boolean;
}

export interface FieldSpec {
  name: string;
  label: string;
  type: "text" | "password" | "number";
  pattern: string | null;
  hint: string | null;
  max_length: number | null;
}

export interface LoginInitResponse {
  broker: string;
  auth_kind: AuthKind;
  redirect_url: string | null;
  fields: FieldSpec[] | null;
}

export interface SessionResponse {
  session_id: string;
  broker: string;
  user_id: string | null;
}

export interface SessionStatusResponse {
  alive: boolean;
  broker: string;
  session_id: string;
  user_id: string | null;
}

export type Action = "BUY" | "SELL";
export type ProductType = "CNC" | "MIS";
export type PriceType = "MARKET" | "LIMIT";
export type Exchange = "NSE" | "BSE";

export interface OrderRequest {
  symbol: string;
  exchange: Exchange;
  action: Action;
  quantity: number;
  price_type?: PriceType;
  product?: ProductType;
  price?: number | null;
}

export interface OrderResult {
  request: OrderRequest;
  status: "PLACED" | "FAILED";
  broker_order_id: string | null;
  error_code: string | null;
  error_message: string | null;
  submitted_at: string;
}

export interface FirstTimeItem {
  symbol: string;
  exchange: Exchange;
  quantity: number;
  product?: ProductType;
  amo?: boolean;
}

export interface SellItem {
  symbol: string;
  exchange: Exchange;
  quantity: number;
  product?: ProductType;
  amo?: boolean;
}

export interface BuyItem {
  symbol: string;
  exchange: Exchange;
  quantity: number;
  product?: ProductType;
  amo?: boolean;
}

export interface AdjustItem {
  symbol: string;
  exchange: Exchange;
  delta: number;
  product?: ProductType;
  amo?: boolean;
}

export interface RebalancePayload {
  sell?: SellItem[];
  buy_new?: BuyItem[];
  adjust?: AdjustItem[];
}

export interface PortfolioExecuteRequest {
  broker: string;
  session_id: string;
  mode: "first_time" | "rebalance";
  first_time?: FirstTimeItem[];
  rebalance?: RebalancePayload;
}

export interface ExecutionSummary {
  broker: string;
  mode: "first_time" | "rebalance";
  started_at: string;
  finished_at: string;
  successes: OrderResult[];
  failures: OrderResult[];
}

export interface Holding {
  symbol: string;
  exchange: Exchange;
  quantity: number;
  average_price: number | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail?: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await response.text();
  const body = text ? safeJson(text) : null;
  if (!response.ok) {
    const message =
      (body as { detail?: string })?.detail ??
      `Request failed: ${response.status}`;
    throw new ApiError(response.status, String(message), body);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  brokers: () => request<BrokerInfo[]>("/brokers"),

  beginLogin: (broker: string) =>
    request<LoginInitResponse>(`/auth/${broker}/login`),

  completeLogin: (broker: string, fields?: Record<string, string>) =>
    request<SessionResponse>(`/auth/${broker}/login`, {
      method: "POST",
      body: JSON.stringify(fields ? { fields } : {}),
    }),

  sessionStatus: (broker: string, sessionId: string) =>
    request<SessionStatusResponse>(
      `/auth/${broker}/status?session_id=${encodeURIComponent(sessionId)}`,
    ),

  logout: (broker: string, sessionId: string) =>
    request<{ status: string }>(
      `/auth/${broker}/session?session_id=${encodeURIComponent(sessionId)}`,
      { method: "DELETE" },
    ),

  execute: (body: PortfolioExecuteRequest) =>
    request<ExecutionSummary>("/portfolio/execute", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  holdings: (sessionId: string) =>
    request<Holding[]>(
      `/holdings?session_id=${encodeURIComponent(sessionId)}`,
    ),

  events: (limit = 20) =>
    request<ExecutionSummary[]>(`/events?limit=${limit}`),
};
