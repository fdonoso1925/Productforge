"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { referenceKey } from "@/lib/reference";
import { problemSchema } from "@/lib/schemas";
import type { Problem } from "@/lib/types";
import { ErrorBox, Loading, StepNav } from "./step-nav";
import type { StepProps } from "./wizard";

const EMPTY: Problem = {
  title: "",
  audience: "",
  pain: "",
  promised_result: "",
  timeframe: "",
  why_pay: "",
  urgency: 3,
};

export function StepProblem({ state, update, nav }: StepProps) {
  const t = useTranslations("wizard.problem");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const requested = useRef<string | null>(null);
  const loading = state.problems === null && !error;

  // Pide los 5 problemas cuando faltan. El ref evita una segunda llamada (y su costo)
  // si React monta el efecto dos veces en modo estricto.
  useEffect(() => {
    const key = `${state.market}|${state.niche}|${referenceKey(state.reference)}|${attempt}`;
    if (state.problems !== null || requested.current === key) return;
    requested.current = key;
    api.proposeProblems(state.niche, state.market, state.reference).then(
      ({ problems }) => update({ problems, problem: problems[0] ?? null }),
      (e) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, [state.problems, state.niche, state.market, state.reference, attempt, update]);

  const load = () => {
    setError(null);
    setAttempt((n) => n + 1);
    update({ problems: null, problem: null });
  };

  const problem = state.problem;
  const valid = problem !== null && problemSchema.safeParse(problem).success;
  const edit = (patch: Partial<Problem>) => problem && update({ problem: { ...problem, ...patch } });

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold">{t("heading")}</h2>
        {state.problems && (
          <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
            {t("regenerate")}
          </Button>
        )}
      </div>

      {loading && <Loading text={t("loading")} />}
      {error && <ErrorBox message={error} onRetry={load} />}

      {state.problems && !loading && (
        <div className="grid gap-3 md:grid-cols-2">
          {state.problems.map((p, i) => {
            const selected = problem?.title === p.title;
            return (
              <button
                key={`${i}-${p.title}`}
                type="button"
                aria-pressed={selected}
                onClick={() => update({ problem: p })}
                className={`flex flex-col gap-2 rounded-xl border p-4 text-left transition-colors ${
                  selected ? "border-primary ring-2 ring-primary/30" : "hover:bg-muted/60"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium leading-snug">{p.title}</span>
                  <Badge variant={p.urgency >= 4 ? "default" : "secondary"}>
                    {t("urgency", { value: p.urgency })}
                  </Badge>
                </div>
                <span className="text-sm text-muted-foreground">
                  <b>{t("audience")}:</b> {p.audience}
                </span>
                <span className="text-sm text-muted-foreground">
                  <b>{t("result")}:</b> {p.promised_result} · {p.timeframe}
                </span>
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => update({ problem: { ...EMPTY } })}
            className="rounded-xl border border-dashed p-4 text-left text-sm text-muted-foreground hover:bg-muted/60"
          >
            + {t("own")}
          </button>
        </div>
      )}

      {problem && !loading && (
        <div className="grid gap-4 rounded-xl border bg-muted/30 p-4 md:grid-cols-2">
          <h3 className="font-medium md:col-span-2">{t("edit")}</h3>
          <Field label={t("titleField")} className="md:col-span-2">
            <Input maxLength={500} value={problem.title} onChange={(e) => edit({ title: e.target.value })} />
          </Field>
          <Field label={t("audience")}>
            <Textarea maxLength={1000} value={problem.audience} onChange={(e) => edit({ audience: e.target.value })} />
          </Field>
          <Field label={t("timeframe")}>
            <Input maxLength={400} value={problem.timeframe} onChange={(e) => edit({ timeframe: e.target.value })} />
          </Field>
          <Field label={t("pain")}>
            <Textarea maxLength={1000} value={problem.pain} onChange={(e) => edit({ pain: e.target.value })} />
          </Field>
          <Field label={t("result")}>
            <Textarea
              maxLength={1000}
              value={problem.promised_result}
              onChange={(e) => edit({ promised_result: e.target.value })}
            />
          </Field>
        </div>
      )}

      <StepNav onBack={nav.back} onNext={nav.next} nextDisabled={!valid} />
    </section>
  );
}

function Field({ label, className, children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={`flex flex-col gap-1.5 ${className ?? ""}`}>
      <Label>{label}</Label>
      {children}
    </div>
  );
}
