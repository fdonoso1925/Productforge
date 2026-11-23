"use client";

import { useTranslations } from "next-intl";
import {
  canAddExtra,
  FORMAT_ICONS,
  makeMain,
  toggleFormat,
} from "@/lib/formats";
import { FORMATS } from "@/lib/types";
import { StepNav } from "./step-nav";
import type { StepProps } from "./wizard";

/**
 * Formatos del paquete: el primero es el producto principal; tocar otros los suma (o quita) como
 * formatos que el paquete incluye sí o sí, como order bump o bonus. «Hacer principal» cambia cuál
 * es el principal.
 */
export function StepFormat({ state, update, nav }: StepProps) {
  const t = useTranslations("wizard.format");
  const tf = useTranslations("formats");
  const pick = { format: state.format, extraFormats: state.extraFormats };

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold">{t("heading")}</h2>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {FORMATS.map((format) => {
          const Icon = FORMAT_ICONS[format];
          const isMain = state.format === format;
          const isExtra = state.extraFormats.includes(format);
          const blocked = !isMain && !isExtra && !canAddExtra(pick, format);
          return (
            <div
              key={format}
              className={`flex flex-col gap-2 rounded-xl border p-4 transition-colors ${
                isMain
                  ? "border-primary ring-2 ring-primary/30"
                  : isExtra
                    ? "border-primary/60 bg-primary/5"
                    : "hover:bg-muted/60"
              } ${blocked ? "opacity-50" : ""}`}
            >
              <button
                type="button"
                aria-pressed={isMain || isExtra}
                disabled={blocked}
                onClick={() => update(toggleFormat(pick, format))}
                className="flex gap-3 text-left disabled:cursor-not-allowed"
              >
                <Icon
                  className="mt-0.5 size-5 shrink-0 text-primary"
                  aria-hidden
                />
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-2 font-medium">
                    {tf(`${format}.name`)}
                    {isMain && (
                      <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] font-semibold text-primary-foreground">
                        {t("main")}
                      </span>
                    )}
                    {isExtra && (
                      <span className="rounded-full border border-primary/60 px-2 py-0.5 text-[11px] font-semibold text-primary">
                        {t("included")}
                      </span>
                    )}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {tf(`${format}.description`)}
                  </span>
                </span>
              </button>
              {isExtra && (
                <button
                  type="button"
                  onClick={() => update(makeMain(pick, format))}
                  className="self-start text-xs font-medium text-primary hover:underline"
                >
                  {t("makeMain")}
                </button>
              )}
            </div>
          );
        })}
      </div>
      {state.extraFormats.length > 0 && (
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {t("summary", {
            main: tf(`${state.format}.name`),
            extras: state.extraFormats.map((f) => tf(`${f}.name`)).join(", "),
          })}
        </p>
      )}
      <StepNav onBack={nav.back} onNext={nav.next} />
    </section>
  );
}
