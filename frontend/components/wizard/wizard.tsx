"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";
import { Link } from "@/i18n/navigation";
import type { CoverSpec, Format, Market, Niche, PackageOutline, Problem, SalesReference } from "@/lib/types";
import { StepFormat } from "./step-format";
import { StepNiche } from "./step-niche";
import { StepOutline } from "./step-outline";
import { StepProblem } from "./step-problem";
import { StepTemplate } from "./step-template";

const STEPS = ["niche", "problem", "format", "template", "outline"] as const;

export type WizardState = {
  market: Market;
  niche: string;
  problems: Problem[] | null;
  problem: Problem | null;
  format: Format;
  templateId: string;
  // Página de ventas de referencia (opcional): inspira los problemas y todo el paquete.
  reference: SalesReference | null;
  // La portada no entra en `inputsKey`: cambiarla no obliga a rehacer el outline.
  cover: CoverSpec;
  // El outline queda atado a las elecciones con que se creó; si cambian, se rehace.
  built: { key: string; productId: string; outline: PackageOutline; dirty: boolean } | null;
};

export function inputsKey(s: WizardState): string {
  return JSON.stringify([s.market, s.niche, s.problem, s.format, s.templateId, s.reference]);
}

export function Wizard({ niches, defaultMarket }: { niches: Niche[]; defaultMarket: Market }) {
  const t = useTranslations("wizard");
  const [step, setStep] = useState(0);
  const [state, setState] = useState<WizardState>({
    market: defaultMarket,
    niche: "",
    problems: null,
    problem: null,
    format: "pdf_guide",
    templateId: "minimal-clean",
    reference: null,
    cover: { art: "auto", image_id: null },
    built: null,
  });
  const update = useCallback(
    (patch: Partial<WizardState>) => setState((s) => ({ ...s, ...patch })),
    [],
  );
  const go = (to: (s: number) => number) => {
    setStep(to);
    window.scrollTo({ top: 0 });
  };
  const next = () => go((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => go((s) => Math.max(s - 1, 0));
  const nav = { next, back };

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <Link href="/" className="text-sm text-muted-foreground hover:underline">
            ProductForge
          </Link>
        </div>
        <ol className="grid grid-cols-5 gap-2" aria-label={t("title")}>
          {STEPS.map((name, i) => (
            <li key={name}>
              <button
                type="button"
                onClick={() => i < step && setStep(i)}
                disabled={i > step}
                aria-current={i === step ? "step" : undefined}
                className={`w-full border-t-4 pt-2 text-left text-xs font-medium transition-colors sm:text-sm ${
                  i <= step ? "border-primary text-foreground" : "border-muted text-muted-foreground"
                }`}
              >
                {i + 1}. {t(`steps.${name}`)}
              </button>
            </li>
          ))}
        </ol>
      </header>

      {step === 0 && <StepNiche niches={niches} state={state} update={update} nav={nav} />}
      {step === 1 && <StepProblem state={state} update={update} nav={nav} />}
      {step === 2 && <StepFormat state={state} update={update} nav={nav} />}
      {step === 3 && <StepTemplate state={state} update={update} nav={nav} />}
      {step === 4 && <StepOutline state={state} update={update} nav={nav} />}
    </main>
  );
}

export type StepProps = {
  state: WizardState;
  update: (patch: Partial<WizardState>) => void;
  nav: { next: () => void; back: () => void };
};
