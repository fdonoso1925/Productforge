"use client";

import { useTranslations } from "next-intl";
import { FORMAT_ICONS } from "@/lib/formats";
import { FORMATS } from "@/lib/types";
import { StepNav } from "./step-nav";
import type { StepProps } from "./wizard";

export function StepFormat({ state, update, nav }: StepProps) {
  const t = useTranslations("wizard.format");
  const tf = useTranslations("formats");

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-xl font-semibold">{t("heading")}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {FORMATS.map((format) => {
          const Icon = FORMAT_ICONS[format];
          const selected = state.format === format;
          return (
            <button
              key={format}
              type="button"
              aria-pressed={selected}
              onClick={() => update({ format })}
              className={`flex gap-3 rounded-xl border p-4 text-left transition-colors ${
                selected ? "border-primary ring-2 ring-primary/30" : "hover:bg-muted/60"
              }`}
            >
              <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
              <span className="flex flex-col gap-1">
                <span className="font-medium">{tf(`${format}.name`)}</span>
                <span className="text-sm text-muted-foreground">{tf(`${format}.description`)}</span>
              </span>
            </button>
          );
        })}
      </div>
      <StepNav onBack={nav.back} onNext={nav.next} />
    </section>
  );
}
