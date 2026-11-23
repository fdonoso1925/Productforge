"use client";

import { Clapperboard, Download, RefreshCw, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ConfirmButton } from "@/components/product/confirm-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ErrorBox } from "@/components/wizard/step-nav";
import { LEMO_STYLES, lookFromKey, lookKey, type BatchRow, type VideoEngines, type VideoRatio, type VideoRow } from "@/lib/ads";
import { ApiError, api } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { PolicyBadge } from "./policy-badge";

const POLL_MS = 3000;
const SELECT = "h-10 w-full min-w-0 rounded-[12px] border border-border bg-card px-3 text-sm font-semibold";
const RATIOS: VideoRatio[] = ["9x16", "4x5"];

/**
 * Videos de motion graphics del lote: texto e íconos animados con música, uno por ángulo y avatar.
 * La IA escribe el guion una sola vez; volver a componer no la usa. Lee de Supabase con RLS.
 */
export function VideosPanel({ batch }: { batch: BatchRow }) {
  const t = useTranslations("ads.videos");
  const tan = useTranslations("ads.angleNames");
  const [videos, setVideos] = useState<VideoRow[]>([]);
  const [urls, setUrls] = useState<Record<string, { url: string; thumb_url: string | null }>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pairs = useMemo(() => batch.picks.map((p) => ({ angle: p.angle_id, avatar: p.avatar })), [batch.picks]);
  const [pair, setPair] = useState(0);
  const [ratio, setRatio] = useState<VideoRatio>("9x16");
  // Estilo: motion graphics (el motor propio) o Lemo-Opuscar con uno de sus estilos, si está instalado.
  const [engines, setEngines] = useState<VideoEngines | null>(null);
  const [look, setLook] = useState("motion");
  useEffect(() => {
    let alive = true;
    api.adsVideoEngines().then(
      (e) => alive && setEngines(e),
      () => alive && setEngines(null),
    );
    return () => {
      alive = false;
    };
  }, []);

  const load = useCallback(async () => {
    const { data, error: failure } = await createClient()
      .from("ad_videos")
      .select("*")
      .eq("batch_id", batch.id)
      .order("created_at");
    if (failure) throw new Error(failure.message);
    return (data ?? []) as VideoRow[];
  }, [batch.id]);

  const working = videos.some((v) => v.status === "planned" || v.status === "rendering");
  const readyKey = videos.filter((v) => v.status === "ready").map((v) => `${v.id}:${v.storage_path}`).join("|");

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await load();
        if (!alive) return;
        setVideos(next);
        if (next.some((v) => v.status === "planned" || v.status === "rendering")) timer = setTimeout(tick, POLL_MS);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [load, busy]);

  // URLs firmadas de los videos listos (duran 10 min: se piden al cambiar algo).
  useEffect(() => {
    if (!readyKey) return;
    let alive = true;
    const ready = videos.filter((v) => v.status === "ready");
    void Promise.all(ready.map(async (v) => [v.id, await api.adsVideoUrl(v.id)] as const))
      .then((entries) => alive && setUrls(Object.fromEntries(entries)))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
    // `videos` cambia en cada sondeo; `readyKey` resume lo que importa.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readyKey]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setVideos(await load());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const create = () => {
    const chosen = pairs[pair];
    if (!chosen) return;
    void act(() => api.adsVideoCreate(batch.id, { ...chosen, ratio, ...lookFromKey(look) }));
  };

  return (
    <section className="glass flex flex-col gap-4 rounded-[20px] p-4" aria-label={t("title")}>
      <div className="flex max-w-2xl flex-col gap-1">
        <h2 className="flex items-center gap-2 font-semibold">
          <Clapperboard className="size-4" aria-hidden />
          {t("title")}
        </h2>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>

      {pairs.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
          <div className="flex flex-col gap-1">
            <Label htmlFor="video-pair">{t("angle")}</Label>
            <select id="video-pair" value={pair} onChange={(e) => setPair(Number(e.target.value))} className={SELECT}>
              {pairs.map((p, i) => (
                <option key={`${p.angle}|${p.avatar}`} value={i}>
                  {tan(p.angle)} · {p.avatar}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="video-ratio">{t("format")}</Label>
            <select id="video-ratio" value={ratio} onChange={(e) => setRatio(e.target.value as VideoRatio)} className={SELECT}>
              {RATIOS.map((r) => (
                <option key={r} value={r}>
                  {t(`ratios.${r}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="video-look">{t("look")}</Label>
            <select id="video-look" value={look} onChange={(e) => setLook(e.target.value)} className={SELECT}>
              <option value="motion">{t("looks.motion")}</option>
              {engines?.lemo &&
                LEMO_STYLES.map((s) => (
                  <option key={s} value={`lemo:${s}`}>
                    {t(`looks.${s}`)}
                  </option>
                ))}
            </select>
          </div>
          <ConfirmButton
            label={t("create")}
            confirmLabel={t("confirmCreate")}
            onConfirm={create}
            disabled={busy}
            size="default"
            icon={<Clapperboard aria-hidden />}
          />
        </div>
      )}

      {engines && !engines.lemo && <p className="text-xs text-muted-foreground">{t("lemoOff")}</p>}
      {engines?.lemo && look !== "motion" && <p className="text-xs text-muted-foreground">{t("lemoHint")}</p>}
      {error && <ErrorBox message={error} />}
      {working && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
          <span className="size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-hidden />
          {t("working")}
        </p>
      )}

      {videos.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {videos.map((video) => {
            const media = urls[video.id];
            return (
              <li key={video.id} className="flex flex-col gap-3 rounded-[16px] bg-white/5 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{tan(video.angle)}</Badge>
                  <Badge variant="outline">{t(`ratios.${video.ratio}`)}</Badge>
                  <Badge variant="outline">{t(`looks.${video.engine === "lemo" ? (video.style ?? "kinetic") : "motion"}`)}</Badge>
                  <PolicyBadge status={video.policy_status} />
                  {video.meta?.ad_id && <Badge>{t("inMeta")}</Badge>}
                </div>
                {video.status === "ready" && media ? (
                  <video
                    src={media.url}
                    poster={media.thumb_url ?? undefined}
                    controls
                    playsInline
                    preload="none"
                    className={`w-full rounded-[12px] bg-black ${video.ratio === "9x16" ? "aspect-[9/16]" : "aspect-[4/5]"}`}
                  />
                ) : (
                  <div
                    className={`flex w-full items-center justify-center rounded-[12px] bg-black/30 p-4 text-center text-sm text-muted-foreground ${
                      video.ratio === "9x16" ? "aspect-[9/16]" : "aspect-[4/5]"
                    }`}
                  >
                    {video.status === "error" ? t("failed", { error: video.error ?? "?" }) : t(`status.${video.status}`)}
                  </div>
                )}
                {video.script && (
                  <p className="line-clamp-2 text-sm font-medium">{video.script.hook_lines.join(" ")}</p>
                )}
                <p className="truncate text-xs text-muted-foreground">
                  {video.avatar}
                  {video.duration ? ` · ${Math.round(video.duration)} s` : ""}
                </p>
                <div className="flex flex-wrap gap-2">
                  {media && (
                    <a
                      href={media.url}
                      download={video.filename}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-xs font-medium hover:bg-white/10"
                    >
                      <Download className="size-3.5" aria-hidden />
                      {t("download")}
                    </a>
                  )}
                  {video.script && video.status !== "rendering" && video.status !== "planned" && (
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => void act(() => api.adsVideoRender(video.id))}>
                      <RefreshCw aria-hidden />
                      {t("rerender")}
                    </Button>
                  )}
                  {video.script &&
                    video.status !== "rendering" &&
                    video.status !== "planned" &&
                    lookKey({ engine: video.engine ?? "motion", style: video.style ?? null }) !== look &&
                    (look === "motion" || engines?.lemo) && (
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => void act(() => api.adsVideoRender(video.id, lookFromKey(look)))}>
                        <Clapperboard aria-hidden />
                        {t("restyle", { look: t(`looks.${look === "motion" ? "motion" : look.split(":")[1]}`) })}
                      </Button>
                    )}
                  {!video.meta?.ad_id && video.status !== "rendering" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      aria-label={t("delete")}
                      onClick={() => void act(() => api.adsVideoDelete(video.id))}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
