"use client";

import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Link } from "@/i18n/navigation";
import type { BatchRow } from "@/lib/ads";
import { createClient } from "@/lib/supabase/client";

type Row = Pick<BatchRow, "id" | "niche" | "market" | "status" | "brief" | "ratios" | "picks" | "created_at">;

export function AdsList() {
  const t = useTranslations("ads");
  const tc = useTranslations("common");
  const tm = useTranslations("markets");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("list.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("list.hint")}</p>
        </div>
        <Link
          href="/ads/new"
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/80"
        >
          <Plus className="size-4" aria-hidden />
          {t("list.new")}
        </Link>
      </header>
      {error && <ErrorBox message={error} />}
      {!rows && !error && <Loading text={tc("loading")} />}
      {rows && rows.length === 0 && <p className="text-sm text-muted-foreground">{t("list.empty")}</p>}
      <div className="grid gap-3">
        {rows?.map((b) => (
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
