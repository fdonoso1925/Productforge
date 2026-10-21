"use client";

import { GitBranch } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "@/i18n/navigation";
import { createClient } from "@/lib/supabase/client";
import type { HistoryRow } from "@/lib/types";
import { buildVersionTree, flattenTree } from "@/lib/versions";

const COLUMNS = "id, title, niche, market, main_format, template_id, status, parent_product_id, created_at";

/** Árbol de versiones del paquete (el original y sus remodelados / duplicados). */
export function VersionsCard({
  currentId,
  rootId,
  refreshKey,
}: {
  currentId: string;
  rootId: string;
  refreshKey: string;
}) {
  const t = useTranslations("product.versions");
  const tm = useTranslations("markets");
  const th = useTranslations("history.status");
  const locale = useLocale();
  const [loaded, setLoaded] = useState<{ key: string; rows: HistoryRow[] } | null>(null);
  const key = `${rootId}|${refreshKey}`;

  useEffect(() => {
    let alive = true;
    createClient()
      .from("products")
      .select(COLUMNS)
      .or(`id.eq.${rootId},root_product_id.eq.${rootId}`)
      .then(({ data }) => alive && setLoaded({ key, rows: (data ?? []) as HistoryRow[] }));
    return () => {
      alive = false;
    };
  }, [rootId, key]);

  const rows = loaded?.key === key ? loaded.rows : (loaded?.rows ?? []);
  if (rows.length < 2) return null; // sin versiones derivadas no hay árbol que mostrar

  const date = new Intl.DateTimeFormat(locale === "pt" ? "pt-BR" : "es", { dateStyle: "medium" });
  const flat = flattenTree(buildVersionTree(rows));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GitBranch className="size-4" aria-hidden />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-1">
          {flat.map(({ node, depth }) => {
            const current = node.id === currentId;
            return (
              <li key={node.id} style={{ paddingLeft: `${depth * 1.25}rem` }}>
                <Link
                  href={`/products/${node.id}`}
                  aria-current={current ? "page" : undefined}
                  className={`flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg px-3 py-2 text-sm hover:bg-muted ${
                    current ? "bg-primary/10 font-medium" : ""
                  }`}
                >
                  <span className="text-muted-foreground" aria-hidden>
                    {depth === 0 ? "●" : "└"}
                  </span>
                  <span className="min-w-0 truncate">{depth === 0 ? t("original") : (node.title ?? node.niche)}</span>
                  <Badge variant="secondary">{tm(node.market)}</Badge>
                  <span className="text-xs text-muted-foreground">{node.template_id}</span>
                  <span className="text-xs text-muted-foreground">{date.format(new Date(node.created_at))}</span>
                  {node.status !== "ready" && <Badge variant={node.status === "error" ? "destructive" : "secondary"}>{th(node.status)}</Badge>}
                  {current && <span className="text-xs text-primary">{t("current")}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
