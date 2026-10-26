"use client";

import { FileText, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Link } from "@/i18n/navigation";
import type { PageRow } from "@/lib/pages";
import { createClient } from "@/lib/supabase/client";

type Row = Pick<PageRow, "id" | "title" | "market" | "status" | "similarity" | "reference" | "created_at">;

export function PagesList() {
  const t = useTranslations("pages");
  const tc = useTranslations("common");
  const tm = useTranslations("markets");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    // Lectura directa con RLS: solo se ven las páginas propias.
    void createClient()
      .from("sales_pages")
      .select("id, title, market, status, similarity, reference, created_at")
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
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-bold">{t("list.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("list.hint")}</p>
        </div>
        <Link
          href="/pages/new"
          className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:bg-primary/85"
        >
          <Plus className="size-4" aria-hidden />
          {t("list.new")}
        </Link>
      </header>
      {error && <ErrorBox message={error} />}
      {!rows && !error && <Loading text={tc("loading")} />}
      {rows && rows.length === 0 && <p className="rounded-lg border p-4 text-sm text-muted-foreground">{t("list.empty")}</p>}
      <ul className="flex flex-col gap-3">
        {rows?.map((r) => (
          <li key={r.id}>
            <Link href={`/pages/${r.id}`} className="block">
              <Card className="transition-colors hover:bg-secondary/40">
                <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                  <span className="flex min-w-0 items-center gap-3">
                    <FileText className="size-5 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate font-semibold">{r.title}</span>
                      <span className="text-xs text-muted-foreground">
                        {tm(r.market)} · {new Date(r.created_at).toLocaleDateString()}
                        {r.reference ? ` · ${t("list.modeled")}` : ""}
                      </span>
                    </span>
                  </span>
                  <span className="flex items-center gap-2">
                    {r.similarity && r.similarity.level !== "ok" && (
                      <Badge variant="outline" className={r.similarity.level === "block" ? "border-destructive text-destructive" : "border-amber-500 text-amber-600"}>
                        {t(`similarity.${r.similarity.level}`)}
                      </Badge>
                    )}
                    <Badge variant={r.status === "error" ? "destructive" : "secondary"}>{t(`status.${r.status}`)}</Badge>
                  </span>
                </CardContent>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
