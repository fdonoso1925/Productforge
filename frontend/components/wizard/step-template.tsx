"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { TemplateInfo } from "@/lib/types";
import { ErrorBox, Loading, StepNav } from "./step-nav";
import type { StepProps } from "./wizard";

export function StepTemplate({ state, update, nav }: StepProps) {
  const t = useTranslations("wizard.template");
  const tc = useTranslations("common");
  const [templates, setTemplates] = useState<TemplateInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    api
      .templates()
      .then(setTemplates, (e) => setError(String(e?.message ?? e)));
  }, [attempt]);
  const load = () => {
    setError(null);
    setAttempt((n) => n + 1);
  };

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-xl font-semibold">{t("heading")}</h2>
      {!templates && !error && <Loading text={tc("loading")} />}
      {error && <ErrorBox message={error} onRetry={load} />}
      {templates &&
        [
          { key: "base", list: templates.filter((tpl) => !tpl.editorial) },
          { key: "editorial", list: templates.filter((tpl) => tpl.editorial) },
        ]
          .filter((group) => group.list.length > 0)
          .map((group) => (
            <div key={group.key} className="flex flex-col gap-3">
              <div>
                <h3 className="font-semibold">
                  {t(`groups.${group.key}.title`)}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {t(`groups.${group.key}.hint`)}
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {group.list.map((tpl) => {
                  const selected = state.templateId === tpl.id;
                  return (
                    <button
                      key={tpl.id}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => update({ templateId: tpl.id })}
                      className={`flex flex-col overflow-hidden rounded-xl border text-left transition-shadow ${
                        selected
                          ? "border-primary ring-2 ring-primary/40"
                          : "hover:shadow-md"
                      }`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element -- miniatura servida por el backend */}
                      <img
                        src={api.previewUrl(tpl.id)}
                        alt={tpl.name}
                        loading="lazy"
                        className="aspect-[3/2] w-full bg-muted object-cover object-top"
                      />
                      <span className="flex flex-col gap-1 p-3">
                        <span className="flex items-center justify-between gap-2">
                          <span className="font-medium">{tpl.name}</span>
                          <span className="flex gap-1" aria-hidden>
                            {["primary", "secondary", "accent"].map((k) => (
                              <span
                                key={k}
                                className="size-3 rounded-full border"
                                style={{ background: tpl.palette[k] }}
                              />
                            ))}
                          </span>
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {tpl.description}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
      <StepNav onBack={nav.back} onNext={nav.next} nextDisabled={!templates} />
    </section>
  );
}
