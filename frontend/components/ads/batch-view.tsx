"use client";

import { Download, ImageIcon, Languages, Maximize2, Pencil, Repeat2, TrendingUp, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ConfirmButton } from "@/components/product/confirm-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Link, useRouter } from "@/i18n/navigation";
import {
  type AdJobRow,
  type BatchRow,
  type CreativeGroup,
  type CreativeRow,
  groupCreatives,
  isActive,
  type ResultRow,
  worstPolicy,
} from "@/lib/ads";
import { ApiError, type AdExport, api } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { AdsDrive } from "./ads-drive";
import { MetaPanel } from "./meta-panel";
import { CreativeEditor } from "./creative-editor";
import { CreativePreview } from "./creative-preview";
import { ImportPanel } from "./import-panel";
import { IteratePanel } from "./iterate-panel";
import { PolicyBadge } from "./policy-badge";
import { MetricsLine, ResultsPanel } from "./results-panel";

const POLL_MS = 2500;
const URL_REFRESH_MS = 8 * 60 * 1000; // las URLs firmadas duran 10 min

type Data = { batch: BatchRow; creatives: CreativeRow[]; results: ResultRow[]; job: AdJobRow | null };
type PanelKind = "edit" | "results" | "iterate";

export function BatchView({ batchId }: { batchId: string }) {
  const t = useTranslations("ads.batch");
  const tc = useTranslations("common");
  const tm = useTranslations("markets");
  const router = useRouter();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [panel, setPanel] = useState<{ id: string; kind: PanelKind } | null>(null);
  const [exported, setExported] = useState<AdExport | null>(null);
  const [busy, setBusy] = useState(false);
  // Vista previa grande: id del anuncio abierto.
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  // ¿Hay algún proveedor de fotos activo? Si sí, se ofrece ponerle foto a los anuncios ya hechos.
  const [photosOn, setPhotosOn] = useState(false);

  // Lecturas directas a Supabase: RLS garantiza que solo vemos lo nuestro.
  const fetchAll = useCallback(async (): Promise<Data> => {
    const supabase = createClient();
    const [batch, creatives, jobs] = await Promise.all([
      supabase.from("ad_batches").select("*").eq("id", batchId).single(),
      supabase.from("ad_creatives").select("*").eq("batch_id", batchId).order("created_at"),
      supabase
        .from("jobs")
        .select("id, kind, status, progress, error")
        .eq("batch_id", batchId)
        .in("kind", ["ad_plan", "ad_render", "ad_iterate"])
        .order("created_at", { ascending: false })
        .limit(1),
    ]);
    const failure = batch.error ?? creatives.error ?? jobs.error;
    if (failure) throw new Error(failure.message);
    const ids = ((creatives.data ?? []) as CreativeRow[]).map((c) => c.id);
    const results = ids.length
      ? await supabase.from("ad_results").select("*").in("creative_id", ids)
      : { data: [], error: null };
    if (results.error) throw new Error(results.error.message);
    return {
      batch: batch.data as BatchRow,
      creatives: (creatives.data ?? []) as CreativeRow[],
      results: (results.data ?? []) as ResultRow[],
      job: ((jobs.data ?? [])[0] as AdJobRow) ?? null,
    };
  }, [batchId]);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await fetchAll();
        if (!alive) return;
        setData(next);
        setError(null);
        if (isActive(next.job) || ["planning", "rendering"].includes(next.batch.status)) {
          timer = setTimeout(tick, POLL_MS);
        }
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
  }, [fetchAll, nonce]);

  // Las URLs de las imágenes se piden de nuevo cuando cambia lo compuesto (y antes de que venzan).
  const renderedKey = useMemo(
    () =>
      (data?.creatives ?? [])
        .filter((c) => c.status === "rendered")
        .map((c) => `${c.id}:${c.updated_at ?? ""}`)
        .join("|"),
    [data],
  );
  useEffect(() => {
    if (!renderedKey) return;
    let alive = true;
    const load = () =>
      void api
        .adsUrls(batchId)
        .then((next) => alive && setUrls(next))
        .catch(() => undefined);
    load();
    const timer = setInterval(load, URL_REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [batchId, renderedKey]);

  useEffect(() => {
    let alive = true;
    api
      .adsImagesStatus()
      .then((r) => alive && setPhotosOn(r.providers.some((p) => p.enabled && !p.exhausted)))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const groups = useMemo(() => groupCreatives(data?.creatives ?? []), [data]);
  // Las imágenes ya compuestas, en el orden de la pantalla, para recorrerlas en la vista previa.
  const previewable = useMemo(
    () =>
      groups.flatMap((g) => g.items).flatMap((c) => (c.status === "rendered" && urls[c.id] ? [{ creative: c, url: urls[c.id] }] : [])),
    [groups, urls],
  );
  const previewIndex = previewId ? previewable.findIndex((p) => p.creative.id === previewId) : -1;

  if (!data) return <Shell>{error ? <ErrorBox message={error} /> : <Loading text={tc("loading")} />}</Shell>;

  const { batch, creatives, results, job } = data;
  const live = creatives.filter((c) => c.status !== "discarded");
  const rendered = live.filter((c) => c.status === "rendered");
  const pending = live.filter((c) => c.status === "planned" || c.status === "error");
  const withoutPhoto = rendered.filter((c) => !c.base_image_path);
  const working = isActive(job) || batch.status === "planning" || batch.status === "rendering";
  const refresh = () => setNonce((n) => n + 1);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      refresh();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const exportBatch = () =>
    run(async () => {
      setExported(await api.adsExport(batchId));
    });

  const otherMarket = batch.market === "pt-BR" ? "es-LATAM" : "pt-BR";
  const duplicate = async () => {
    setBusy(true);
    setActionError(null);
    try {
      const { batch_id } = await api.adsDuplicate(batchId, otherMarket);
      router.push(`/ads/${batch_id}`);
    } catch (e) {
      setActionError(e instanceof ApiError ? (e.errors.length ? e.errors.join(" · ") : e.message) : String(e));
      setBusy(false);
    }
  };
  const toggle = (id: string, kind: PanelKind) =>
    setPanel(panel?.id === id && panel.kind === kind ? null : { id, kind });

  return (
    <Shell title={batch.brief.product_name} meta={`${tm(batch.market)} · ${batch.niche}`}>
      {batch.status === "planning" && <PlanningPanel job={job} />}
      {batch.status === "error" && live.length === 0 && <ErrorBox message={t("planFailed")} />}
      {job?.status === "error" && live.length > 0 && <ErrorBox message={t("jobFailed")} />}
      {actionError && <ErrorBox message={actionError} />}

      {live.length > 0 && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-primary/5 p-4">
            <div className="text-sm">
              <p className="font-medium">{t("summary", { drafts: groups.length, rendered: rendered.length, total: live.length })}</p>
              <p className="text-muted-foreground">{t("reviewHint")}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => run(() => api.adsRender(batchId))} disabled={busy || working || pending.length === 0}>
                <Wand2 aria-hidden />
                {t("render", { count: pending.length })}
              </Button>
              <Button variant="outline" onClick={exportBatch} disabled={busy || working || rendered.length === 0}>
                <Download aria-hidden />
                {t("export")}
              </Button>
              {photosOn && withoutPhoto.length > 0 && (
                <Button
                  variant="outline"
                  onClick={() => run(() => api.adsRender(batchId, [], true))}
                  disabled={busy || working}
                  title={t("recomposePhotosHint")}
                >
                  <ImageIcon aria-hidden />
                  {t("recomposePhotos", { count: withoutPhoto.length })}
                </Button>
              )}
              <ConfirmButton
                size="default"
                label={t("duplicate", { market: tm(otherMarket) })}
                confirmLabel={t("duplicateConfirm")}
                onConfirm={() => void duplicate()}
                disabled={busy || working}
                icon={<Languages aria-hidden />}
              />
            </div>
          </div>
          {exported && (
            <div className="flex flex-wrap items-center gap-4 rounded-lg border p-3 text-sm" aria-live="polite">
              <span>{t("exportReady", { count: exported.images })}</span>
              <a href={exported.zip_url} download={exported.zip_name} className="text-primary underline underline-offset-2">
                {t("downloadZip")}
              </a>
              <a href={exported.csv_url} download className="text-primary underline underline-offset-2">
                {t("downloadCsv")}
              </a>
            </div>
          )}
          {batch.parent_batch_id && (
            <p className="text-sm text-muted-foreground">
              {t("duplicatedFrom")}{" "}
              <Link href={`/ads/${batch.parent_batch_id}`} className="text-primary underline underline-offset-2">
                {t("original")}
              </Link>
            </p>
          )}
          {rendered.length > 0 && <AdsDrive batchId={batchId} refreshKey={renderedKey} />}
          {rendered.length > 0 && <MetaPanel batchId={batchId} market={batch.market} refreshKey={renderedKey} />}
          {rendered.length > 0 && <ImportPanel onImported={refresh} />}
          {working && batch.status !== "planning" && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
              <span className="size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-hidden />
              {t("rendering", { done: job?.progress.done ?? 0, total: job?.progress.total ?? pending.length })}
            </p>
          )}

          <div className="grid gap-4">
            {groups.map((g) => (
              <GroupCard
                key={g.id}
                group={g}
                urls={urls}
                onPreview={setPreviewId}
                results={results}
                parent={creatives.find((c) => c.id === g.lead.parent_creative_id)}
                panel={panel?.id === g.id ? panel.kind : null}
                disabled={busy || working}
                onToggle={(kind) => toggle(g.id, kind)}
                onChanged={() => {
                  setPanel(null);
                  refresh();
                }}
                onResults={refresh}
                onDiscard={() => run(() => Promise.all(g.items.map((c) => api.adsDiscard(c.id))))}
                onRender={() => run(() => api.adsRender(batchId, g.items.filter((c) => c.status !== "rendered").map((c) => c.id)))}
              />
            ))}
          </div>
        </>
      )}
      {previewable.length > 0 && previewIndex >= 0 && (
        <CreativePreview
          items={previewable}
          index={previewIndex}
          onIndex={(i) => setPreviewId(previewable[i]?.creative.id ?? null)}
          onClose={() => setPreviewId(null)}
        />
      )}
    </Shell>
  );
}

function Shell({ title, meta, children }: { title?: string; meta?: string; children: React.ReactNode }) {
  const t = useTranslations("ads.batch");
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold">{title ?? t("title")}</h1>
          {meta && <p className="text-sm text-muted-foreground">{meta}</p>}
        </div>
        <Link href="/ads" className="text-sm text-muted-foreground hover:underline">
          {t("back")}
        </Link>
      </header>
      {children}
    </main>
  );
}

function PlanningPanel({ job }: { job: AdJobRow | null }) {
  const t = useTranslations("ads.batch");
  const done = job?.progress.done ?? 0;
  const total = job?.progress.total ?? 0;
  return (
    <div className="flex flex-col gap-3 rounded-xl border p-4" aria-live="polite">
      <p className="flex items-center gap-2 font-medium">
        <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-hidden />
        {t("planning")}
      </p>
      <p className="text-sm text-muted-foreground">{total > 0 ? t("planningProgress", { done, total }) : t("planningHint")}</p>
    </div>
  );
}

function GroupCard({
  group,
  urls,
  onPreview,
  results,
  parent,
  panel,
  disabled,
  onToggle,
  onChanged,
  onResults,
  onDiscard,
  onRender,
}: {
  group: CreativeGroup;
  urls: Record<string, string>;
  onPreview: (id: string) => void;
  results: ResultRow[];
  parent?: CreativeRow;
  panel: PanelKind | null;
  disabled: boolean;
  onToggle: (kind: PanelKind) => void;
  onChanged: () => void;
  onResults: () => void;
  onDiscard: () => void;
  onRender: () => void;
}) {
  const t = useTranslations("ads");
  const { lead, items } = group;
  const draft = lead.copy;
  const unrendered = items.some((c) => c.status !== "rendered");
  const notes = lead.policy_notes?.notes ?? [];
  const ids = new Set(items.map((c) => c.id));
  const own = results.filter((r) => ids.has(r.creative_id));

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{t(`angleNames.${lead.angle}`)}</Badge>
          <Badge variant="outline">{t(`templates.${lead.template_id}`)}</Badge>
          <span className="text-xs text-muted-foreground">{lead.avatar}</span>
          {lead.parent_creative_id && (
            <Badge variant="secondary" title={parent?.copy.image.headline}>
              {t("batch.iteration")}
            </Badge>
          )}
          <span className="ml-auto flex items-center gap-2">
            {lead.pre_score !== null && (
              <span className="text-xs text-muted-foreground" title={lead.score_notes?.explanation}>
                {t("batch.score", { score: lead.pre_score })}
              </span>
            )}
            <PolicyBadge status={worstPolicy(items)} />
          </span>
        </div>

        <div className="flex flex-wrap items-start gap-3">
          {items.map((c) => (
            <Thumb key={c.id} creative={c} url={urls[c.id]} onOpen={() => onPreview(c.id)} />
          ))}
        </div>

        <div className="flex flex-col gap-1 text-sm">
          <p className="font-medium">{draft.image.headline}</p>
          {draft.image.subheadline && <p className="text-muted-foreground">{draft.image.subheadline}</p>}
          <p className="mt-1">{draft.ad.primary_short}</p>
          {draft.variant_note && <p className="text-xs text-muted-foreground">{draft.variant_note}</p>}
        </div>

        {own.length > 0 && <MetricsLine rows={own} />}

        {(notes.length > 0 || lead.policy_notes?.rewrite) && (
          <details className="rounded-lg bg-muted/40 p-3 text-sm">
            <summary className="cursor-pointer font-medium">{t("batch.policyNotes", { count: notes.length })}</summary>
            <ul className="mt-2 list-disc pl-5">
              {notes.map((n) => (
                <li key={n.rule + n.text}>{n.text}</li>
              ))}
            </ul>
            {lead.policy_notes?.rewrite && (
              <p className="mt-2">
                <strong>{t("batch.rewrite")}:</strong> {lead.policy_notes.rewrite}
              </p>
            )}
            {lead.score_notes?.improvement && (
              <p className="mt-2">
                <strong>{t("batch.improve")}:</strong> {lead.score_notes.improvement}
              </p>
            )}
          </details>
        )}

        <div className="flex flex-wrap gap-2">
          <Button variant={panel === "edit" ? "default" : "outline"} size="sm" onClick={() => onToggle("edit")} disabled={disabled}>
            <Pencil aria-hidden />
            {t("batch.edit")}
          </Button>
          <Button variant={panel === "results" ? "default" : "outline"} size="sm" onClick={() => onToggle("results")}>
            <TrendingUp aria-hidden />
            {t("batch.results")}
          </Button>
          <Button variant={panel === "iterate" ? "default" : "outline"} size="sm" onClick={() => onToggle("iterate")} disabled={disabled}>
            <Repeat2 aria-hidden />
            {t("batch.iterate")}
          </Button>
          {unrendered && (
            <Button variant="outline" size="sm" onClick={onRender} disabled={disabled}>
              <Wand2 aria-hidden />
              {t("batch.renderGroup")}
            </Button>
          )}
          <ConfirmButton label={t("batch.discard")} confirmLabel={t("batch.discardConfirm")} onConfirm={onDiscard} disabled={disabled} />
        </div>

        {panel === "edit" && <CreativeEditor creative={lead} onSaved={onChanged} onClose={() => onToggle("edit")} />}
        {panel === "results" && <ResultsPanel group={group} results={results} onChanged={onResults} />}
        {panel === "iterate" && <IteratePanel group={group} onDone={onChanged} disabled={disabled} />}
      </CardContent>
    </Card>
  );
}

const ASPECT: Record<string, string> = { "4x5": "4 / 5", "9x16": "9 / 16", "1x1": "1 / 1" };

function Thumb({ creative, url, onOpen }: { creative: CreativeRow; url?: string; onOpen: () => void }) {
  const t = useTranslations("ads");
  const width = creative.ratio === "9x16" ? "w-28" : "w-36";
  const label = t(`wizard.formats.${creative.ratio}`);
  return (
    <figure className="flex flex-col gap-1">
      <div
        className={`${width} overflow-hidden rounded-lg border bg-muted/40`}
        style={{ aspectRatio: ASPECT[creative.ratio] }}
      >
        {creative.status === "rendered" && url ? (
          <button
            type="button"
            onClick={onOpen}
            aria-label={t("batch.preview.open", { format: label })}
            title={t("batch.preview.open", { format: label })}
            className="group relative block size-full cursor-zoom-in"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada temporal de Storage */}
            <img src={url} alt={`${creative.copy.image.headline} (${label})`} className="size-full object-cover" loading="lazy" />
            <span className="absolute right-1 bottom-1 flex size-7 items-center justify-center rounded-full bg-black/60 text-white opacity-90 group-hover:bg-black/80">
              <Maximize2 className="size-3.5" aria-hidden />
            </span>
          </button>
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-1 p-2 text-center text-xs text-muted-foreground">
            <ImageIcon className="size-4" aria-hidden />
            {creative.status === "error" ? t("batch.renderError") : t("batch.notRendered")}
          </div>
        )}
      </div>
      <figcaption className="text-xs text-muted-foreground">{label}</figcaption>
    </figure>
  );
}

