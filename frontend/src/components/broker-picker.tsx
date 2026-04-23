import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSessions } from "@/hooks/use-sessions";
import {
  api,
  type ApiError,
  type AuthKind,
  type BrokerInfo,
} from "@/lib/api";

type ActiveBroker = {
  name: string;
  display_name: string;
  auth_kind: AuthKind;
};

type Resumed = ActiveBroker & { sessionId: string };

interface Props {

  onSelect: (broker: ActiveBroker) => void;

  onResume: (resumed: Resumed) => void;
}

const AUTH_KIND_LABEL: Record<AuthKind, string> = {
  oauth_redirect: "OAuth",
  credentials_form: "Credentials",
  api_key_only: "API key",
};

export function BrokerPicker({ onSelect, onResume }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["brokers"],
    queryFn: api.brokers,
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-destructive">
        Could not load brokers. Is the backend running on :8000?
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground text-center">
        Select a broker to connect
      </p>
      <div className="space-y-2">
        {data?.map((b) => (
          <BrokerRow
            key={b.name}
            broker={b}
            onSelect={onSelect}
            onResume={onResume}
          />
        ))}
      </div>
    </div>
  );
}

function BrokerRow({
  broker,
  onSelect,
  onResume,
}: {
  broker: BrokerInfo;
  onSelect: Props["onSelect"];
  onResume: Props["onResume"];
}) {
  const qc = useQueryClient();
  const { sessions, remove } = useSessions();
  const cachedSessionId = sessions[broker.name];

  const status = useQuery({
    queryKey: ["session-status", broker.name, cachedSessionId],
    queryFn: () => api.sessionStatus(broker.name, cachedSessionId!),
    enabled: Boolean(cachedSessionId),
    staleTime: 30_000,
  });

  const logout = useMutation({
    mutationFn: () => api.logout(broker.name, cachedSessionId!),
    onSuccess: () => {
      remove(broker.name);
      qc.invalidateQueries({ queryKey: ["session-status", broker.name] });
      toast.success(`Disconnected from ${broker.display_name}`);
    },
    onError: (err) => toast.error((err as ApiError).message),
  });

  const hasCached = Boolean(cachedSessionId);
  const isAlive = hasCached && status.data?.alive === true;
  const isChecking = hasCached && status.isLoading;

  useEffect(() => {
    if (hasCached && status.data && status.data.alive === false) {
      remove(broker.name);
    }
  }, [hasCached, status.data, broker.name, remove]);

  return (
    <Card>
      <CardContent className="flex items-center justify-between p-4">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium">{broker.display_name}</span>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs font-normal">
              {AUTH_KIND_LABEL[broker.auth_kind]}
            </Badge>
            <StatusText
              configured={broker.configured}
              isChecking={isChecking}
              isAlive={isAlive}
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isAlive ? (
            <>
              <Button
                size="sm"
                onClick={() =>
                  onResume({
                    name: broker.name,
                    display_name: broker.display_name,
                    auth_kind: broker.auth_kind,
                    sessionId: cachedSessionId!,
                  })
                }
              >
                Reconnect
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={logout.isPending}
                onClick={() => logout.mutate()}
              >
                Logout
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant={broker.configured ? "default" : "secondary"}
              disabled={!broker.configured || isChecking}
              onClick={() =>
                onSelect({
                  name: broker.name,
                  display_name: broker.display_name,
                  auth_kind: broker.auth_kind,
                })
              }
            >
              Connect
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function StatusText({
  configured,
  isChecking,
  isAlive,
}: {
  configured: boolean;
  isChecking: boolean;
  isAlive: boolean;
}) {
  if (!configured) {
    return (
      <span className="text-xs text-muted-foreground">
        Not configured in .env
      </span>
    );
  }
  if (isChecking) {
    return <span className="text-xs text-muted-foreground">Checking…</span>;
  }
  if (isAlive) {
    return <span className="text-xs text-foreground">Connected</span>;
  }
  return <span className="text-xs text-muted-foreground">Ready</span>;
}
