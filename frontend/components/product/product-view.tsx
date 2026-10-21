"use client";

import { Download, FileArchive } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { FORMAT_ICONS } from "@/lib/formats";
import { createClient } from "@/lib/supabase/client";
import type { FileRow, ItemRow, JobRow, ProductRow } from "@/lib/types";
import { CommercialCard } from "./commercial-card";

const POLL_MS = 2500;

type Data = { product: ProductRow; items: ItemRow[]; files: FileRow[]; job: JobRow | null };

export function ProductView({ productId }: { productId: string }) {
  const t = useTranslations("product");
  const tc = useTranslations("common");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Lecturas directas a Supabase: RLS garantiza que solo vemos lo nuestro.
  const fetchAll = useCallback(async (): Promise<Data | null> => {
    const supabase = createClient();
    const [product, items, files, jobs] = await Promise.all([
      supabase.from("products").select("*").eq("id", productId).single(),
      supabase.from("product_items").select("id, role, format, title, status, order").eq("product_id", productId),
      supabase.from("files").select("id, product_item_id, file_type, storage_path, size").eq("product_id", productId),
      supabase
        .from("jobs")
        .select("id, status, progress, error, created_at")
        .eq("product_id", productId)
        .order("created_at", { ascending: false })
        .limit(1),
    ]);
    const failure = product.error ?? items.error ?? files.error ?? jobs.error;
    if (failure) throw new Error(failure.message);
    return {
      product: product.data as ProductRow,
      items: sortItems((items.data ?? []) as ItemRow[]),
      files: (files.data ?? []) as FileRow[],
      job: ((jobs.data ?? [])[0] as JobRow) ?? null,
    };
  }, [productId]);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await fetchAll();
        if (!alive || !next) return;
        setData(next);
        setError(null);
        const active = next.job && ["queued", "running"].includes(next.job.status);
        if (active || next.product.status === "generating") timer = setTimeout(tick, POLL_MS);
      } catch (e) {
        if (alive) {
          setError(e instanceof Error ? e.message : String(e));
          timer = setTimeout(tick, POLL_MS * 2);
        }
      }
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [fetchAll]);

  if (!data) return <Shell>{error ? <ErrorBox message={error} /> : <Loading text={tc("loading")} />}</Shell>;

  const { product, items, files, job } = data;
  const running = product.status === "generating" || (job && ["queued", "running"].includes(job.status));
  const zip = files.find((f) => f.file_type === "zip");

  return (
    <Shell title={product.title ?? product.niche}>
      {running && job && <ProgressPanel job={job} items={items} />}
      {!running && job?.status === "error" && <ErrorBox message={t("failed", { error: job.error ?? "?" })} />}
      {!running && product.status === "error" && job?.status === "done" && (
        <p className="rounded-lg bg-amber-500/10 p-3 text-sm">{t("partial")}</p>
      )}

      {!running && files.length > 0 && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-primary/5 p-4">
            <span className="font-medium">{t("ready")}</span>
            {zip && <DownloadButton file={zip} label={t("downloadZip")} primary />}
          </div>
          <p className="text-xs text-muted-foreground">{t("onedrive")}</p>
          <div className="grid gap-3">
            {items.map((item) => (
              <ItemFiles key={item.id} item={item} files={files.filter((f) => f.product_item_id === item.id)} />
            ))}
          </div>
          {product.commercial && (
            <CommercialCard
              sheet={product.commercial}
              files={files.filter((f) => !f.product_item_id && f.file_type !== "zip")}
            />
          )}
        </>
      )}
    </Shell>
  );
}

function Shell({ title, children }: { title?: string; children: React.ReactNode }) {
  const tc = useTranslations("common");
  return (
    <main className="mx-auto flex w-full min-w-0 max-w-4xl flex-1 flex-col gap-6 px-4 py-8">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <Link href="/" className="text-sm text-muted-foreground hover:underline">
          {tc("home")}
        </Link>
      </div>
      {children}
    </main>
  );
}

function ProgressPanel({ job, items }: { job: JobRow; items: ItemRow[] }) {
  const t = useTranslations("product");
  const p = job.progress ?? {};
  const total = p.total || items.length || 1;
  // Las piezas son ~85 % del trabajo; ficha comercial y ZIP, el resto.
  const stageBonus = { items: 0, commercial: 5, zip: 10, done: 15 }[p.stage ?? "items"];
  const value = Math.round(((p.done ?? 0) / total) * 85 + stageBonus);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("generating")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <div className="flex justify-between text-sm">
            <span>{t(`stages.${p.stage ?? "items"}`)}</span>
            <span className="tabular-nums">{value}%</span>
          </div>
          <Progress value={value} />
        </div>
        <ul className="flex flex-col gap-2">
          {items.map((item) => {
            const status = p.items?.[item.id] ?? item.status;
            return (
              <li key={item.id} className="flex items-center justify-between gap-3 text-sm">
                <ItemLabel item={item} />
                <StatusBadge status={status} />
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function ItemLabel({ item }: { item: ItemRow }) {
  const tr = useTranslations("roles");
  const Icon = FORMAT_ICONS[item.format];
  return (
    <span className="flex min-w-0 items-center gap-2">
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <span className="truncate">{item.title}</span>
      <span className="shrink-0 text-xs text-muted-foreground">· {tr(item.role)}</span>
    </span>
  );
}

function StatusBadge({ status }: { status: ItemRow["status"] }) {
  const t = useTranslations("product.itemStatus");
  const variant = status === "ready" ? "default" : status === "error" ? "destructive" : "secondary";
  return (
    <Badge variant={variant} className={status === "generating" ? "animate-pulse" : undefined}>
      {t(status)}
    </Badge>
  );
}

function ItemFiles({ item, files }: { item: ItemRow; files: FileRow[] }) {
  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <ItemLabel item={item} />
        {item.status === "error" && <StatusBadge status="error" />}
      </div>
      <div className="flex flex-wrap gap-2">
        {files.map((f) => (
          <DownloadButton key={f.id} file={f} label={fileLabel(f, files)} />
        ))}
      </div>
    </div>
  );
}

export function DownloadButton({ file, label, primary }: { file: FileRow; label: string; primary?: boolean }) {
  const [pending, setPending] = useState(false);
  const download = async () => {
    setPending(true);
    try {
      const { url } = await api.downloadUrl(file.id);
      const name = file.storage_path.split("/").pop() ?? "archivo";
      // URL firmada externa (Supabase Storage); un <a> temporal fuerza la descarga.
      const link = document.createElement("a");
      link.href = `${url}&download=${encodeURIComponent(name)}`;
      link.click();
    } finally {
      setPending(false);
    }
  };
  const Icon = primary ? FileArchive : Download;
  return (
    <Button
      variant={primary ? "default" : "outline"}
      size={primary ? "lg" : "sm"}
      onClick={download}
      disabled={pending}
      title={file.storage_path.split("/").pop()}
    >
      <Icon aria-hidden />
      {label}
    </Button>
  );
}

/** "PDF", "XLSX"… y, si hay varios del mismo tipo (un CSV por pestaña), "CSV 1", "CSV 2"… */
function fileLabel(file: FileRow, siblings: FileRow[]): string {
  const same = siblings.filter((f) => f.file_type === file.file_type);
  const type = file.file_type.toUpperCase();
  if (same.length < 2) return type;
  const sorted = [...same].sort((a, b) => a.storage_path.localeCompare(b.storage_path));
  return `${type} ${sorted.findIndex((f) => f.id === file.id) + 1}`;
}

const ROLE_ORDER = { main: 0, order_bump: 1, bonus: 2 } as const;

function sortItems(items: ItemRow[]): ItemRow[] {
  return [...items].sort((a, b) => ROLE_ORDER[a.role] - ROLE_ORDER[b.role] || a.order - b.order);
}
