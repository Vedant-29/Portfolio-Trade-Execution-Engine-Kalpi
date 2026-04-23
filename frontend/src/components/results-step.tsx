import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { ExecutionSummary, OrderResult } from "@/lib/api";

const ERROR_LABELS: Record<string, string> = {
  INSUFFICIENT_FUNDS: "Insufficient funds",
  MARKET_CLOSED: "Market closed",
  AMO_NOT_SUPPORTED: "AMO not supported for this order type",
  CIRCUIT_LIMIT: "Hit circuit limit",
  CIRCUIT_LIMIT_UPPER: "Hit upper circuit",
  CIRCUIT_LIMIT_LOWER: "Hit lower circuit",
  INVALID_SYMBOL: "Unknown symbol",
  RATE_LIMIT: "Rate limited",
  AUTH_EXPIRED: "Session expired — please reconnect",
  AUTH_FAILED: "Broker rejected authentication",
  IP_NOT_WHITELISTED: "IP not whitelisted in broker console",
  NETWORK: "Broker network error",
  ORDER_REJECTED: "Order rejected",
  UNKNOWN_ERROR: "Unknown error",
};

function friendlyErrorLabel(code: string | null): string {
  if (!code) return "Failed";
  return ERROR_LABELS[code] ?? code;
}

interface Props {
  summary: ExecutionSummary;
  onRunAgain: () => void;
  onNewBroker: () => void;
}

export function ResultsStep({ summary, onRunAgain, onNewBroker }: Props) {
  const total = summary.successes.length + summary.failures.length;
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-muted-foreground">
                {summary.broker} · {summary.mode}
              </div>
              <div className="text-base font-medium mt-1">
                {summary.successes.length} of {total} placed
              </div>
            </div>
            <Badge
              variant={summary.failures.length === 0 ? "default" : "secondary"}
              className="font-normal"
            >
              {summary.failures.length === 0 ? "All placed" : "Partial"}
            </Badge>
          </div>

          {summary.successes.length > 0 && (
            <>
              <Separator />
              <div>
                <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">
                  Placed
                </div>
                <ul className="space-y-1.5">
                  {summary.successes.map((r, i) => (
                    <li key={i} className="text-sm">
                      <OrderLine r={r} />
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {summary.failures.length > 0 && (
            <>
              <Separator />
              <div>
                <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">
                  Failed
                </div>
                <ul className="space-y-2">
                  {summary.failures.map((r, i) => (
                    <li key={i} className="text-sm">
                      <OrderLine r={r} />
                      <div className="mt-0.5 ml-3 space-y-0.5">
                        <div className="text-xs font-medium text-foreground">
                          {friendlyErrorLabel(r.error_code)}
                        </div>
                        {r.error_message && (
                          <div className="text-xs text-muted-foreground">
                            {r.error_message}
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <div className="flex gap-2 justify-center">
        <Button onClick={onRunAgain}>Run again</Button>
        <Button variant="outline" onClick={onNewBroker}>
          Switch broker
        </Button>
      </div>
    </div>
  );
}

function OrderLine({ r }: { r: OrderResult }) {
  return (
    <span className="flex items-center gap-2">
      <span className="text-muted-foreground w-10 tabular-nums text-xs">
        {r.request.action}
      </span>
      <span className="font-medium">{r.request.symbol}</span>
      <span className="text-muted-foreground">×{r.request.quantity}</span>
      {r.broker_order_id && (
        <span className="text-xs text-muted-foreground ml-auto">
          #{r.broker_order_id}
        </span>
      )}
    </span>
  );
}
