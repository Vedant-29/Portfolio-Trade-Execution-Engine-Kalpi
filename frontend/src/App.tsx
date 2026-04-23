import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AuthStep } from "@/components/auth-step";
import { BrokerPicker } from "@/components/broker-picker";
import { ExecuteStep } from "@/components/execute-step";
import { HistoryScreen } from "@/components/history-screen";
import { ResultsStep } from "@/components/results-step";
import { Separator } from "@/components/ui/separator";
import { useSessions } from "@/hooks/use-sessions";
import type { AuthKind, ExecutionSummary } from "@/lib/api";

type Step = "broker" | "auth" | "execute" | "results";
type Screen = Step | "history";

interface ActiveSession {
  broker: string;
  brokerDisplayName: string;
  authKind: AuthKind;
  sessionId: string;
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("broker");

  const [stepBeforeHistory, setStepBeforeHistory] = useState<Step>("broker");
  const [selectedBroker, setSelectedBroker] = useState<{
    name: string;
    display_name: string;
    auth_kind: AuthKind;
  } | null>(null);
  const [session, setSession] = useState<ActiveSession | null>(null);
  const [summary, setSummary] = useState<ExecutionSummary | null>(null);
  const { set: cacheSession, remove: uncacheSession } = useSessions();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sid = params.get("session_id");
    const broker = params.get("broker");
    if (sid && broker) {
      cacheSession(broker, sid);
      setSession({
        broker,
        brokerDisplayName: broker,
        authKind: "oauth_redirect",
        sessionId: sid,
      });
      setScreen("execute");
      window.history.replaceState({}, "", "/");
      toast.success(`Connected to ${broker}`);
    }
  }, [cacheSession]);

  function openHistory() {
    if (screen !== "history") setStepBeforeHistory(screen as Step);
    setScreen("history");
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12 bg-background">
      <div className="w-full max-w-xl">
        <header className="mb-8 text-center relative">
          <h1 className="text-2xl font-medium tracking-tight">
            Portfolio Trade Execution Engine
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Kalpi Builder · connect a broker and execute a portfolio in one
            click
          </p>
          <button
            type="button"
            onClick={screen === "history" ? () => setScreen(stepBeforeHistory) : openHistory}
            className="absolute right-0 top-1 text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
          >
            {screen === "history" ? "Back" : "History"}
          </button>
        </header>

        {screen !== "history" && (
          <>
            <StepIndicator step={screen as Step} />
            <Separator className="my-6" />
          </>
        )}

        {screen === "broker" && (
          <BrokerPicker
            onSelect={(broker) => {
              setSelectedBroker(broker);
              setScreen("auth");
            }}
            onResume={(resumed) => {
              setSession({
                broker: resumed.name,
                brokerDisplayName: resumed.display_name,
                authKind: resumed.auth_kind,
                sessionId: resumed.sessionId,
              });
              setScreen("execute");
              toast.success(`Reconnected to ${resumed.display_name}`);
            }}
          />
        )}

        {screen === "auth" && selectedBroker && (
          <AuthStep
            broker={selectedBroker}
            onAuthenticated={(sessionId) => {
              cacheSession(selectedBroker.name, sessionId);
              setSession({
                broker: selectedBroker.name,
                brokerDisplayName: selectedBroker.display_name,
                authKind: selectedBroker.auth_kind,
                sessionId,
              });
              setScreen("execute");
            }}
            onBack={() => {
              setSelectedBroker(null);
              setScreen("broker");
            }}
          />
        )}

        {screen === "execute" && session && (
          <ExecuteStep
            session={session}
            onExecuted={(s) => {
              setSummary(s);
              setScreen("results");
            }}
            onDisconnect={() => {
              uncacheSession(session.broker);
              setSession(null);
              setSelectedBroker(null);
              setScreen("broker");
            }}
            onSwitchBroker={() => {

              setSession(null);
              setSelectedBroker(null);
              setScreen("broker");
            }}
          />
        )}

        {screen === "results" && summary && (
          <ResultsStep
            summary={summary}
            onRunAgain={() => setScreen("execute")}
            onNewBroker={() => {
              setSession(null);
              setSelectedBroker(null);
              setSummary(null);
              setScreen("broker");
            }}
          />
        )}

        {screen === "history" && (
          <HistoryScreen onBack={() => setScreen(stepBeforeHistory)} />
        )}
      </div>
    </div>
  );
}

function StepIndicator({ step }: { step: Step }) {
  const steps: Array<{ id: Step; label: string }> = [
    { id: "broker", label: "1. Broker" },
    { id: "auth", label: "2. Connect" },
    { id: "execute", label: "3. Execute" },
    { id: "results", label: "4. Results" },
  ];
  const activeIndex = steps.findIndex((s) => s.id === step);
  return (
    <div className="flex items-center justify-between text-xs text-muted-foreground">
      {steps.map((s, i) => (
        <span
          key={s.id}
          className={
            i <= activeIndex
              ? "text-foreground font-medium"
              : "text-muted-foreground"
          }
        >
          {s.label}
        </span>
      ))}
    </div>
  );
}
