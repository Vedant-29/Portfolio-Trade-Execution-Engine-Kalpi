import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ApiError, type AuthKind, type FieldSpec } from "@/lib/api";

interface Props {
  broker: { name: string; display_name: string; auth_kind: AuthKind };
  onAuthenticated: (sessionId: string) => void;
  onBack: () => void;
}

export function AuthStep({ broker, onAuthenticated, onBack }: Props) {
  const init = useQuery({
    queryKey: ["begin-login", broker.name],
    queryFn: () => api.beginLogin(broker.name),
  });

  if (init.isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }

  if (init.error) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-destructive">
          {(init.error as ApiError).message}
        </p>
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
      </div>
    );
  }

  const data = init.data!;

  if (data.auth_kind === "oauth_redirect" && data.redirect_url) {
    return (
      <OAuthRedirect
        broker={broker}
        redirectUrl={data.redirect_url}
        onBack={onBack}
      />
    );
  }

  if (data.auth_kind === "credentials_form" && data.fields) {
    return (
      <CredentialsForm
        broker={broker}
        fields={data.fields}
        onAuthenticated={onAuthenticated}
        onBack={onBack}
      />
    );
  }

  if (data.auth_kind === "api_key_only") {
    return (
      <OneClickConnect
        broker={broker}
        onAuthenticated={onAuthenticated}
        onBack={onBack}
      />
    );
  }

  return <p className="text-sm text-destructive">Unknown auth flow.</p>;
}

function OAuthRedirect({
  broker,
  redirectUrl,
  onBack,
}: {
  broker: Props["broker"];
  redirectUrl: string;
  onBack: () => void;
}) {
  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <p className="text-sm">
          Log in with {broker.display_name}. You'll be redirected to their site,
          then brought back here.
        </p>
        <div className="flex gap-2">
          <Button onClick={() => (window.location.href = redirectUrl)}>
            Continue to {broker.display_name}
          </Button>
          <Button variant="outline" onClick={onBack}>
            Back
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CredentialsForm({
  broker,
  fields,
  onAuthenticated,
  onBack,
}: {
  broker: Props["broker"];
  fields: FieldSpec[];
  onAuthenticated: (sessionId: string) => void;
  onBack: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.name, ""])),
  );
  const mutation = useMutation({
    mutationFn: () => api.completeLogin(broker.name, values),
    onSuccess: (res) => onAuthenticated(res.session_id),
    onError: (err) => toast.error((err as ApiError).message),
  });

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <p className="text-sm">
          Sign in to {broker.display_name} to continue.
        </p>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          {fields.map((f) => (
            <div key={f.name} className="space-y-1.5">
              <Label htmlFor={f.name}>{f.label}</Label>
              <Input
                id={f.name}
                type={f.type}
                required
                inputMode={f.pattern?.includes("0-9") ? "numeric" : undefined}
                pattern={f.pattern ?? undefined}
                maxLength={f.max_length ?? undefined}
                value={values[f.name]}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [f.name]: e.target.value }))
                }
              />
              {f.hint && (
                <p className="text-xs text-muted-foreground">{f.hint}</p>
              )}
            </div>
          ))}
          <div className="flex gap-2 pt-2">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Connecting…" : "Connect"}
            </Button>
            <Button type="button" variant="outline" onClick={onBack}>
              Back
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function OneClickConnect({
  broker,
  onAuthenticated,
  onBack,
}: {
  broker: Props["broker"];
  onAuthenticated: (sessionId: string) => void;
  onBack: () => void;
}) {
  const mutation = useMutation({
    mutationFn: () => api.completeLogin(broker.name),
    onSuccess: (res) => onAuthenticated(res.session_id),
    onError: (err) => toast.error((err as ApiError).message),
  });

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <p className="text-sm">
          {broker.display_name} uses API-key authentication from environment
          variables. No additional input needed.
        </p>
        <div className="flex gap-2">
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? "Connecting…" : "Connect"}
          </Button>
          <Button variant="outline" onClick={onBack}>
            Back
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
