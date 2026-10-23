"use client";

import { Plus, Trophy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ImagesStatus } from "./images-status";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Link } from "@/i18n/navigation";
import type { BatchRow } from "@/lib/ads";
import { normalizeSearch } from "@/lib/ads";
import { createClient } from "@/lib/supabase/client";

type Row = Pick<BatchRow, "id" | "niche" | "market" | "status" | "brief" | "ratios" | "picks" | "created_at">;

export function AdsList() {
  const t = useTranslations("ads");
  const tc = useTranslations("common");
  const tm = useTranslations("markets");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [market, setMarket] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    let alive = true;
    // Lectura directa con RLS: solo se ven los lotes propios.
    void createClient()
      .from("ad_batches")
      .select("id, niche, market, status, brief, ratios, picks, created_at")
      .order("created_at", { ascending: false })
      .limit(100)
      .then(({ data, error: failure }) => {
        if (!alive) return;
        if (failure) setError(failure.message);
        else setRows((data ?? []) as Row[]);
      });
    return () => {
      alive = false;
    };
  }, []);

  const needle = normalizeSearch(q);
  const shown = rows?.filter(
    (b) =>
      (!market || b.market === market) &&
      (!status || b.status === status) &&
      (!needle || normalizeSearch(`${b.brief.product_name} ${b.niche}`).includes(needle)),
  );

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("list.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("list.hint")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/ads/insights"
            className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            <Trophy className="size-4" aria-hidden />
            {t("list.insights")}
          </Link>
          <Link
            href="/ads/new"
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/80"
          >
            <Plus className="size-4" aria-hidden />
            {t("list.new")}
          </Link>
        </div>
      </header>
      <ImagesStatus />
      <div className="grid gap-3 sm:grid-cols-3">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("list.search")} aria-label={t("list.search")} />
        <select
          value={market}
          onChange={(e) => setMarket(e.target.value)}
          className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm"
          aria-label={t("list.market")}
        >
          <option value="">{t("list.allMarkets")}</option>
          <option value="es-LATAM">{tm("es-LATAM")}</option>
          <option value="pt-BR">{tm("pt-BR")}</option>
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm"
          aria-label={t("list.status")}
        >
          <option value="">{t("list.allStatuses")}</option>
          {["planning", "review", "rendering", "ready", "error"].map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </select>
      </div>
      {error && <ErrorBox message={error} />}
      {!rows && !error && <Loading text={tc("loading")} />}
      {rows && rows.length === 0 && <p className="text-sm text-muted-foreground">{t("list.empty")}</p>}
      {rows && rows.length > 0 && shown?.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("list.noMatches")}</p>
      )}
      <div className="grid gap-3">
        {shown?.map((b) => (
          <Link key={b.id} href={`/ads/${b.id}`} className="rounded-xl focus-visible:ring-3 focus-visible:ring-ring/50">
            <Card className="transition-colors hover:bg-muted/40">
              <CardContent className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{b.brief.product_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {tm(b.market)} · {b.niche} · {new Date(b.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    {t("list.drafts", { count: b.picks.reduce((n, p) => n + p.count, 0) })} · {b.ratios.length}{" "}
                    {t("list.formats")}
                  </span>
                  <Badge variant={b.status === "error" ? "destructive" : "secondary"}>{t(`status.${b.status}`)}</Badge>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </main>
  );
}
