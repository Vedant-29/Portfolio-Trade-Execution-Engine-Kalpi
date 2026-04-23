import { useMutation } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type ApiError,
  type ExecutionSummary,
  type PortfolioExecuteRequest,
} from "@/lib/api";

function isMarketOpenIST(now: Date = new Date()): boolean {
  const istParts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Kolkata",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(now);
  const weekday = istParts.find((p) => p.type === "weekday")?.value;
  const hour = Number(istParts.find((p) => p.type === "hour")?.value ?? 0);
  const minute = Number(istParts.find((p) => p.type === "minute")?.value ?? 0);
  if (weekday === "Sat" || weekday === "Sun") return false;
  const nowMinutes = hour * 60 + minute;
  const open = 9 * 60 + 15;
  const close = 15 * 60 + 30;
  return nowMinutes >= open && nowMinutes <= close;
}

interface Session {
  broker: string;
  brokerDisplayName: string;
  sessionId: string;
}

interface Props {
  session: Session;
  onExecuted: (summary: ExecutionSummary) => void;
  onDisconnect: () => void;
  onSwitchBroker: () => void;
}

const FIRST_TIME_REGULAR = JSON.stringify(
  [
    { symbol: "IDEA", exchange: "NSE", quantity: 1, product: "CNC" },
    { symbol: "YESBANK", exchange: "NSE", quantity: 1, product: "CNC" },
  ],
  null,
  2,
);

const FIRST_TIME_AMO = JSON.stringify(
  [
    {
      symbol: "IDEA",
      exchange: "NSE",
      quantity: 1,
      product: "CNC",
      price_type: "LIMIT",
      price: 9.5,
    },
    {
      symbol: "YESBANK",
      exchange: "NSE",
      quantity: 1,
      product: "CNC",
      price_type: "LIMIT",
      price: 22.0,
    },
  ],
  null,
  2,
);

const REBALANCE_REGULAR = JSON.stringify(
  {
    sell: [{ symbol: "IDEA", exchange: "NSE", quantity: 1 }],
    buy_new: [{ symbol: "SOUTHBANK", exchange: "NSE", quantity: 1 }],
    adjust: [{ symbol: "YESBANK", exchange: "NSE", delta: 1 }],
  },
  null,
  2,
);

const REBALANCE_AMO = JSON.stringify(
  {
    sell: [
      {
        symbol: "IDEA",
        exchange: "NSE",
        quantity: 1,
        price_type: "LIMIT",
        price: 9.5,
      },
    ],
    buy_new: [
      {
        symbol: "SOUTHBANK",
        exchange: "NSE",
        quantity: 1,
        price_type: "LIMIT",
        price: 29.0,
      },
    ],
    adjust: [
      {
        symbol: "YESBANK",
        exchange: "NSE",
        delta: 1,
        price_type: "LIMIT",
        price: 22.0,
      },
    ],
  },
  null,
  2,
);

function exampleFor(
  mode: "first_time" | "rebalance",
  amo: boolean,
): string {
  if (mode === "first_time") {
    return amo ? FIRST_TIME_AMO : FIRST_TIME_REGULAR;
  }
  return amo ? REBALANCE_AMO : REBALANCE_REGULAR;
}

function collectItems(
  mode: "first_time" | "rebalance",
  parsedValue: unknown,
): Array<Record<string, unknown> | null> {
  if (mode === "first_time") {
    return Array.isArray(parsedValue) ? parsedValue : [];
  }
  if (!parsedValue || typeof parsedValue !== "object") return [];
  const v = parsedValue as Record<string, unknown>;
  const out: Array<Record<string, unknown> | null> = [];
  for (const key of ["sell", "buy_new", "adjust"] as const) {
    const bucket = v[key];
    if (Array.isArray(bucket)) out.push(...bucket);
  }
  return out;
}

export function ExecuteStep({
  session,
  onExecuted,
  onDisconnect,
  onSwitchBroker,
}: Props) {
  const [mode, setMode] = useState<"first_time" | "rebalance">("first_time");
  const marketOpen = isMarketOpenIST();
  const [amo, setAmo] = useState<boolean>(false);
  const [text, setText] = useState<string>(() => exampleFor("first_time", false));

  const lastAutoExample = useRef<string>(exampleFor("first_time", false));

  function setTextIfUnedited(next: string) {
    if (text !== lastAutoExample.current) return;
    lastAutoExample.current = next;
    setText(next);
  }

  const parsed = useMemo(() => {
    try {
      const v = JSON.parse(text);
      return { ok: true as const, value: v };
    } catch (e) {
      return { ok: false as const, error: (e as Error).message };
    }
  }, [text]);

  const amoValidation = useMemo(() => {
    if (!amo || !parsed.ok) return { valid: true as const, missingCount: 0 };
    const items = collectItems(mode, parsed.value);
    const missing = items.filter(
      (it) => it?.price_type !== "LIMIT" || typeof it?.price !== "number",
    ).length;
    return missing > 0
      ? { valid: false as const, missingCount: missing }
      : { valid: true as const, missingCount: 0 };
  }, [amo, parsed, mode]);

  function resetToAmoTemplate() {
    const template = exampleFor(mode, true);
    lastAutoExample.current = template;
    setText(template);
  }

  const mutation = useMutation({
    mutationFn: (body: PortfolioExecuteRequest) => api.execute(body),
    onSuccess: onExecuted,
    onError: (err) => toast.error((err as ApiError).message),
  });

  function handleExecute() {
    if (!parsed.ok) {
      toast.error("Fix the JSON before executing");
      return;
    }

    const withAmo = <T extends { amo?: boolean }>(item: T): T => ({
      ...item,
      amo: item.amo ?? amo,
    });

    type Base = { first_time?: unknown; rebalance?: unknown };
    const extras: Base = {};
    if (mode === "first_time") {
      const items = parsed.value as PortfolioExecuteRequest["first_time"];
      extras.first_time = (items ?? []).map(withAmo);
    } else {
      const payload = parsed.value as NonNullable<
        PortfolioExecuteRequest["rebalance"]
      >;
      extras.rebalance = {
        sell: (payload.sell ?? []).map(withAmo),
        buy_new: (payload.buy_new ?? []).map(withAmo),
        adjust: (payload.adjust ?? []).map(withAmo),
      };
    }

    const body: PortfolioExecuteRequest = {
      broker: session.broker,
      session_id: session.sessionId,
      mode,
      ...(extras as Partial<PortfolioExecuteRequest>),
    };
    mutation.mutate(body);
  }

  function handleModeChange(next: "first_time" | "rebalance") {
    setMode(next);
    setTextIfUnedited(exampleFor(next, amo));
  }

  function handleAmoChange(next: boolean) {
    setAmo(next);
    setTextIfUnedited(exampleFor(mode, next));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          Connected to{" "}
          <Badge variant="outline" className="ml-1 font-normal">
            {session.brokerDisplayName}
          </Badge>
        </span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground underline underline-offset-2"
            onClick={onSwitchBroker}
          >
            Switch broker
          </button>
          <span className="text-muted-foreground/40">·</span>
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground underline underline-offset-2"
            onClick={onDisconnect}
          >
            Disconnect
          </button>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="space-y-1.5">
            <Label>Mode</Label>
            <Select value={mode} onValueChange={(v) => handleModeChange(v as typeof mode)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="first_time">
                  First-time portfolio (BUY each item)
                </SelectItem>
                <SelectItem value="rebalance">
                  Rebalance (SELL → BUY new → ADJUST)
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="payload">
              {mode === "first_time" ? "Target holdings" : "Rebalance payload"}
            </Label>
            <Textarea
              id="payload"
              rows={10}
              spellCheck={false}
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="font-mono text-xs"
            />
            {!parsed.ok && (
              <p className="text-xs text-destructive">JSON error: {parsed.error}</p>
            )}
          </div>

          <div className="flex items-start gap-2.5">
            <Checkbox
              id="amo"
              checked={amo}
              onCheckedChange={(v) => handleAmoChange(v === true)}
              className="mt-0.5"
            />
            <div className="space-y-0.5">
              <Label htmlFor="amo" className="cursor-pointer">
                Place as after-market order (AMO)
              </Label>
              <p className="text-xs text-muted-foreground">
                {marketOpen
                  ? "Use AMO only for next-session orders; during market hours regular orders execute faster."
                  : "NSE is closed right now. AMO queues until tomorrow's 9:15 AM IST open."}
              </p>
              {amo && (
                <p className="text-xs text-muted-foreground">
                  Payload above switched to LIMIT with indicative prices.
                  Edit the <code className="text-xs">price</code> on each
                  item to match current LTP — if the limit is too far
                  from market when NSE opens, the order won't fill.
                </p>
              )}
              {amo && session.broker === "groww" && (
                <p className="text-xs text-destructive">
                  Groww's SDK doesn't expose an AMO parameter — orders will
                  be rejected. Use another broker for after-market queuing.
                </p>
              )}
            </div>
          </div>

          {amo && parsed.ok && !amoValidation.valid && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 space-y-1">
              <p className="text-xs font-medium text-destructive">
                {amoValidation.missingCount === 1
                  ? "1 item is missing "
                  : `${amoValidation.missingCount} items are missing `}
                <code className="text-xs">&quot;price_type&quot;: &quot;LIMIT&quot;</code>
                {" and "}
                <code className="text-xs">&quot;price&quot;</code>.
              </p>
              <p className="text-xs text-muted-foreground">
                AMO orders need both. Edit each item, or{" "}
                <button
                  type="button"
                  onClick={resetToAmoTemplate}
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  reset to AMO template
                </button>
                .
              </p>
            </div>
          )}

          <div className="pt-2">
            <Button
              onClick={handleExecute}
              disabled={
                !parsed.ok ||
                mutation.isPending ||
                (amo && !amoValidation.valid)
              }
            >
              {mutation.isPending ? "Executing…" : "Execute"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
