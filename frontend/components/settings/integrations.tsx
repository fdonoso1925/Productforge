"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { api } from "@/lib/api";
import type { IntegrationProvider, IntegrationStatus, Integrations } from "@/lib/types";
import { IntegrationCard } from "./integration-card";

const PROVIDERS: IntegrationProvider[] = ["meta", "hotmart"];

/** Meta Ads y Hotmart: qué está conectado y los formularios para conectar lo que falta. */
export function IntegrationsSection() {
  const t = useTranslations("settings.integrations");
  const [data, setData] = useState<Integrations | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.integrations().then(
      (d) => setData(d),
      (e) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, []);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading text="…" />;

  const update = (provider: IntegrationProvider, next: IntegrationStatus) => setData({ ...data, [provider]: next });

  return (
    <section aria-labelledby="integrations" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="integrations" className="text-xl font-semibold">
          {t("title")}
        </h2>
        <ul className="flex flex-wrap gap-2 text-xs">
          {PROVIDERS.map((p) => (
            <li
              key={p}
              className={`rounded-full border px-3 py-1 ${data[p].connected ? "border-primary/60 text-primary" : "border-border text-muted-foreground"}`}
            >
              {t(`${p}.title`)}: {data[p].connected ? t("connected") : t("notConnected")}
            </li>
          ))}
        </ul>
      </div>
      {PROVIDERS.map((p) => (
        <IntegrationCard key={p} provider={p} status={data[p]} onChange={(next) => update(p, next)} />
      ))}
    </section>
  );
}
