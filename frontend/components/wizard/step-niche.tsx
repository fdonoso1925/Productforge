"use client";

import { useTranslations } from "next-intl";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { nicheSchema } from "@/lib/schemas";
import type { Market, Niche, SalesReference } from "@/lib/types";
import { ReferencePanel } from "./reference-panel";
import { StepNav } from "./step-nav";
import type { StepProps } from "./wizard";

const MARKETS: Market[] = ["pt-BR", "es-LATAM"];

export function StepNiche({ niches, state, update, nav }: StepProps & { niches: Niche[] }) {
  const t = useTranslations("wizard.niche");
  const tm = useTranslations("markets");
  const suggestions = niches.filter((n) => n.market === state.market);
  const valid = nicheSchema.safeParse(state.niche).success;

  // Cambiar nicho o mercado invalida los problemas propuestos.
  const set = (patch: { niche?: string; market?: Market; reference?: SalesReference | null }) =>
    update({ ...patch, problems: null, problem: null });

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-xl font-semibold">{t("heading")}</h2>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-medium">{t("market")}</legend>
        <div className="flex flex-wrap gap-2">
          {MARKETS.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={state.market === m}
              onClick={() => set({ market: m, niche: "", reference: null })}
              className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${
                state.market === m ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted"
              }`}
            >
              {tm(m)}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">{t("suggested")}</span>
        <div className="flex flex-wrap gap-2">
          {suggestions.map((n) => (
            <button
              key={n.id}
              type="button"
              aria-pressed={state.niche === n.name}
              onClick={() => set({ niche: n.name })}
              className={`rounded-lg border px-3 py-2 text-sm transition-colors ${
                state.niche === n.name ? "border-primary bg-primary/10 font-medium" : "hover:bg-muted"
              }`}
            >
              {n.name}
            </button>
          ))}
        </div>
      </div>

      <div className="flex max-w-md flex-col gap-2">
        <Label htmlFor="custom-niche">{t("custom")}</Label>
        <Input
          id="custom-niche"
          maxLength={120}
          placeholder={t("customPlaceholder")}
          value={suggestions.some((n) => n.name === state.niche) ? "" : state.niche}
          onChange={(e) => set({ niche: e.target.value })}
        />
      </div>

      <ReferencePanel
        // La referencia se resume en el idioma del mercado: cambiar de mercado la descarta (arriba).
        key={state.market}
        market={state.market}
        value={state.reference}
        onChange={(reference) =>
          // Sin nicho escrito, el de la página sirve de punto de partida.
          set({ reference, ...(reference && !state.niche.trim() && reference.niche_hint ? { niche: reference.niche_hint.slice(0, 120) } : {}) })
        }
      />

      <StepNav onNext={nav.next} nextDisabled={!valid} />
    </section>
  );
}
