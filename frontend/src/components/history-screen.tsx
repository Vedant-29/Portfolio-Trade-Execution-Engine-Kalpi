import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ApiError, type ExecutionSummary, type OrderResult } from "@/lib/api";

interface Props {
  onBack: () => void;
}

const ERROR_LABELS: Record<string, string> = {
  INSUFFICIENT_FUNDS: "Insufficient funds",
  MARKET_CLOSED: "Market closed",
  AMO_NOT_SUPPORTED: "AMO not supported",
  CIRCUIT_LIMIT: "Hit circuit",
  CIRCUIT_LIMIT_UPPER: "Upper circuit",
  CIRCUIT_LIMIT_LOWER: "Lower circuit",
  INVALID_SYMBOL: "Unknown symbol",
  RATE_LIMIT: "Rate limited",
  AUTH_EXPIRED: "Session expired",
  AUTH_FAILED: "Auth rejected",
  IP_NOT_WHITELISTED: "IP not whitelisted",
  NETWORK: "Network error",
  ORDER_REJECTED: "Rejected",
  UNKNOWN_ERROR: "Unknown error",
};

function friendlyErrorLabel(code: string | null): string {
  if (!code) return "Failed";
  return ERROR_LABELS[code] ?? code;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const time = d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
  if (sameDay) return `Today · ${time}`;
  return `${d.toLocaleDateString(undefined, { day: "numeric", month: "short" })} · ${time}`;
}

export function HistoryScreen({ onBack }: Props) {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["events"],
    queryFn: () => api.events(50),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-medium">Execution history</h2>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>{isFetching ? "Refreshing…" : "Auto-refresh 15s"}</span>
          <button
            type="button"
            onClick={() => refetch()}
            className="underline underline-offset-2 hover:text-foreground"
          >
            Refresh
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">
          {(error as ApiError).message}
        </p>
      )}

      {data && data.length === 0 && (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            No executions yet. Run one from the Execute step.
          </CardContent>
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="space-y-2">
          {data.map((summary, i) => (
            <HistoryRow key={`${summary.started_at}-${i}`} summary={summary} />
          ))}
        </div>
      )}

      <div className="pt-2 flex justify-center">
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
      </div>
    </div>
  );
}

function HistoryRow({ summary }: { summary: ExecutionSummary }) {
  const [expanded, setExpanded] = useState(false);
  const total = summary.successes.length + summary.failures.length;
  const allPlaced = summary.failures.length === 0 && summary.successes.length > 0;
  const allFailed = summary.successes.length === 0 && summary.failures.length > 0;

  return (
    <Card>
      <CardContent className="p-4">
        <button
          type="button"
          onClick={() => setExpanded((x) => !x)}
          className="flex w-full items-center justify-between text-left"
        >
          <div className="space-y-1">
            <div className="text-sm font-medium">
              {summary.successes.length} of {total} placed{" "}
              <span className="text-muted-foreground font-normal">
                · {summary.broker} · {summary.mode}
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              {formatTime(summary.started_at)}
            </div>
          </div>
          <Badge
            variant={allPlaced ? "default" : allFailed ? "destructive" : "secondary"}
            className="font-normal"
          >
            {allPlaced ? "All placed" : allFailed ? "All failed" : "Partial"}
          </Badge>
        </button>

        {expanded && (
          <>
            <Separator className="my-3" />
            {summary.successes.length > 0 && (
              <div className="mb-3">
                <div className="mb-1.5 text-xs uppercase tracking-wide text-muted-foreground">
                  Placed
                </div>
                <ul className="space-y-1">
                  {summary.successes.map((r, i) => (
                    <li key={i} className="text-xs">
                      <OrderLine r={r} />
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {summary.failures.length > 0 && (
              <div>
                <div className="mb-1.5 text-xs uppercase tracking-wide text-muted-foreground">
                  Failed
                </div>
                <ul className="space-y-1.5">
                  {summary.failures.map((r, i) => (
                    <li key={i} className="text-xs">
                      <OrderLine r={r} />
                      <div className="ml-6 mt-0.5 text-[11px] text-muted-foreground">
                        {friendlyErrorLabel(r.error_code)}
                        {r.error_message && ` — ${r.error_message}`}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function OrderLine({ r }: { r: OrderResult }) {
  return (
    <span className="flex items-center gap-2">
      <span className="w-8 text-[11px] tabular-nums text-muted-foreground">
        {r.request.action}
      </span>
      <span className="font-medium">{r.request.symbol}</span>
      <span className="text-muted-foreground">×{r.request.quantity}</span>
      {r.broker_order_id && (
        <span className="ml-auto text-[11px] text-muted-foreground">
          #{r.broker_order_id}
        </span>
      )}
    </span>
  );
}
