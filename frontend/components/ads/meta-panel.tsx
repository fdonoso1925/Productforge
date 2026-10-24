"use client";

import { RefreshCw, Rocket } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { ConfirmButton } from "@/components/product/confirm-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorBox } from "@/components/wizard/step-nav";
import type { MetaBatch, MetaStatus } from "@/lib/ads";
import { ApiError, api } from "@/lib/api";

const POLL_MS = 3000;
const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";

function message(e: unknown): string {
  if (e instanceof ApiError) return e.errors.length ? e.errors.join(" · ") : e.message;
  return e instanceof Error ? e.message : String(e);
}

/**
 * Subir el lote a Meta Ads. Campaña, conjunto y anuncios se crean SIEMPRE en pausa: no se gasta nada
 * hasta que el usuario los active en Ads Manager. Las métricas se leen solas cada 6 horas.
 */
export function MetaPanel({
  batchId,
  market,
  refreshKey,
}: {
  batchId: string;
  market: string;
  refreshKey: string;
}) {
  const t = useTranslations("ads.meta");
  const [account, setAccount] = useState<MetaStatus | null>(null);
  const [state, setState] = useState<MetaBatch | null>(null);
  const [nonce, setNonce] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ link: "", objective: "traffic", budget: "5", countries: "" });

  useEffect(() => {
    let alive = true;
    void api
      .adsMetaStatus()
      .then((s) => {
        if (!alive) return;
        setAccount(s);
        setForm((f) => (f.countries ? f : { ...f, countries: (s.default_countries[market.slice(0, 2)] ?? []).join(", ") }));
      })
      .catch(() => alive && setAccount(null)); // Meta es un extra: nunca estorba el resto
    return () => {
      alive = false;
    };
  }, [market]);

  useEffect(() => {
    if (!account?.configured) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await api.adsMeta(batchId);
        if (!alive) return;
        setState(next);
        if (next.status === "publishing") timer = setTimeout(tick, POLL_MS);
      } catch {
        if (alive) setState(null);
      }
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [batchId, account?.configured, refreshKey, nonce]);

  if (!account) return null;

  if (!account.configured) {
    return (
      <p className="text-xs text-muted-foreground">
        {t("notConfigured", { missing: account.missing.join(", ") })}
      </p>
    );
  }

  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      setNonce((n) => n + 1);
    } catch (e) {
      setError(message(e));
    }
  };

  const countries = form.countries
    .split(/[,\s]+/)
    .map((c) => c.trim().toUpperCase())
    .filter(Boolean);
  const budget = Number(form.budget);
  const valid = /^https:\/\/[^\s/]+\.[^\s/]+/.test(form.link.trim()) && budget > 0 && countries.length > 0;
  const publishing = state?.status === "publishing";
  const published = state && state.status !== "none";

  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-muted/30 p-4" aria-label={t("title")}>
      <div>
        <h3 className="flex items-center gap-2 font-semibold">
          <Rocket className="size-4" aria-hidden />
          {t("title")}
        </h3>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
        {account.account_name && (
          <p className="text-xs text-muted-foreground">
            {t("account", { name: account.account_name, currency: account.currency ?? "" })}
          </p>
        )}
        {account.account_active === false && <p className="text-xs text-destructive">{t("inactive")}</p>}
        {account.error && <p className="text-xs text-destructive">{account.error}</p>}
      </div>

      {published && state && (
        <div className="flex flex-col gap-2 text-sm" aria-live="polite">
          <p>
            {publishing && (
              <span className="mr-2 inline-block size-3 animate-spin rounded-full border-2 border-primary border-t-transparent align-middle" aria-hidden />
            )}
            {t(`status.${state.status}`, { uploaded: state.uploaded, total: state.total, failed: state.failed })}
            {state.skipped > 0 && <span className="text-muted-foreground"> · {t("skipped", { count: state.skipped })}</span>}
          </p>
          {state.error && state.status !== "done" && <p className="text-destructive">{state.error}</p>}
          {state.status === "done" && <p className="text-muted-foreground">{t("paused")}</p>}
          {state.active_ads > 0 && <p className="font-medium text-amber-600">{t("active", { count: state.active_ads })}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={publishing || !state.campaign_id}
              onClick={() => void run(() => api.adsMetaSync(batchId))}
            >
              <RefreshCw aria-hidden />
              {t("sync")}
            </Button>
            {state.synced_at && (
              <span className="text-xs text-muted-foreground">
                {t("syncedAt", { date: new Date(state.synced_at).toLocaleString() })}
              </span>
            )}
          </div>
        </div>
      )}

      {(!published || state?.status === "partial" || state?.status === "error") && (
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label htmlFor="meta-link">{t("link")}</Label>
              <Input
                id="meta-link"
                type="url"
                inputMode="url"
                placeholder="https://"
                value={form.link}
                onChange={(e) => setForm({ ...form, link: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">{t("linkHint")}</p>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="meta-objective">{t("objective")}</Label>
              <select
                id="meta-objective"
                value={form.objective}
                onChange={(e) => setForm({ ...form, objective: e.target.value })}
                className={SELECT_CLASS}
              >
                <option value="traffic">{t("traffic")}</option>
                {account.sales_available && <option value="sales">{t("sales")}</option>}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="meta-budget">{t("budget", { currency: account.currency ?? "" })}</Label>
              <Input
                id="meta-budget"
                type="number"
                min={1}
                step="0.5"
                value={form.budget}
                onChange={(e) => setForm({ ...form, budget: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label htmlFor="meta-countries">{t("countries")}</Label>
              <Input
                id="meta-countries"
                value={form.countries}
                onChange={(e) => setForm({ ...form, countries: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">{t("countriesHint")}</p>
            </div>
          </div>
          {error && <ErrorBox message={error} />}
          <div>
            <ConfirmButton
              label={state?.status === "partial" || state?.status === "error" ? t("retry") : t("publish")}
              confirmLabel={t("confirm")}
              onConfirm={() =>
                void run(() =>
                  api.adsMetaPublish(batchId, {
                    link_url: form.link.trim(),
                    objective: form.objective as "traffic" | "sales",
                    daily_budget: budget,
                    countries,
                  }),
                )
              }
              disabled={!valid || publishing}
              icon={<Rocket aria-hidden />}
            />
          </div>
        </div>
      )}
      {published && error && <ErrorBox message={error} />}
    </section>
  );
}
