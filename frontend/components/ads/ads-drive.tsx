"use client";

import { Cloud, ExternalLink } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import type { AdDrive } from "@/lib/ads";
import { ApiError, api } from "@/lib/api";

const POLL_MS = 3000;

/** Copia del lote a Google Drive. Storage sigue siendo el respaldo: si Drive falla, se reintenta. */
export function AdsDrive({ batchId, refreshKey }: { batchId: string; refreshKey: string }) {
  const t = useTranslations("ads.drive");
  const [data, setData] = useState<AdDrive | null>(null);
  const [nonce, setNonce] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await api.adsDrive(batchId);
        if (!alive) return;
        setData(next);
        if (next.status === "uploading") timer = setTimeout(tick, POLL_MS);
      } catch {
        if (alive) setData(null); // Drive es un extra: nunca estorba el resto
      }
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [batchId, refreshKey, nonce]);

  if (!data) return null;

  if (!data.connected) {
    return (
      <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Cloud className="size-3.5" aria-hidden />
        {t("notConnected")} ·{" "}
        <Link href="/settings" className="underline underline-offset-2">
          {t("connectLink")}
        </Link>
      </p>
    );
  }

  const start = async () => {
    setError(null);
    try {
      await api.adsDriveStart(batchId);
      setNonce((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  const uploading = data.status === "uploading";
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
      <span className="flex items-center gap-2">
        <Cloud className="size-4 text-muted-foreground" aria-hidden />
        {data.status === "none" ? t("none") : t("files", { uploaded: data.uploaded, total: data.total })}
      </span>
      {uploading && (
        <span className="flex items-center gap-2 text-muted-foreground" aria-live="polite">
          <span className="size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-hidden />
          {t("syncing")}
        </span>
      )}
      {data.status === "error" && <span className="text-destructive">{t("failed", { count: data.failed })}</span>}
      {!uploading && (
        <Button variant="outline" size="sm" onClick={start}>
          {data.status === "error" ? t("retry") : data.status === "done" ? t("again") : t("copy")}
        </Button>
      )}
      {data.folder_url && (
        <a
          href={data.folder_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-primary underline underline-offset-2"
        >
          {t("openFolder")}
          <ExternalLink className="size-3.5" aria-hidden />
        </a>
      )}
      {error && <span className="text-destructive">{error}</span>}
    </div>
  );
}
