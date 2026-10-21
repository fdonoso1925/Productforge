"use client";

import { Cloud, ExternalLink } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import type { ProductDrive } from "@/lib/types";

const POLL_MS = 3000;

/** Estado de la copia del paquete en Google Drive, con reintento manual. */
export function DriveStatus({ productId, refreshKey }: { productId: string; refreshKey: string }) {
  const t = useTranslations("product.driveSync");
  const [data, setData] = useState<ProductDrive | null>(null);
  // Sube al pedir una subida para volver a consultar y reanudar el polling.
  const [nonce, setNonce] = useState(0);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await api.productDrive(productId);
        if (!alive) return;
        setData(next);
        setError(false);
        // Mientras sube (o falta por subir en el proceso de generación) se sigue consultando.
        if (next.syncing) timer = setTimeout(tick, POLL_MS);
      } catch {
        if (alive) setError(true);
      }
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [productId, refreshKey, nonce]);

  if (error || !data) return null; // el estado de Drive es un extra: nunca estorba el resto

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

  const unsynced = data.pending + data.failed;
  const retry = async () => {
    await api.productDriveSync(productId).catch(() => undefined);
    setNonce((n) => n + 1);
  };

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
      <span className="flex items-center gap-2">
        <Cloud className="size-4 text-muted-foreground" aria-hidden />
        {t("files", { uploaded: data.uploaded, total: data.total })}
      </span>
      {data.syncing && (
        <span className="flex items-center gap-2 text-muted-foreground" aria-live="polite">
          <span className="size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-hidden />
          {t("syncing")}
        </span>
      )}
      {!data.syncing && data.failed > 0 && <span className="text-destructive">{t("failed", { count: data.failed })}</span>}
      {!data.syncing && data.pending > 0 && <span className="text-muted-foreground">{t("pending", { count: data.pending })}</span>}
      {!data.syncing && unsynced > 0 && (
        <Button variant="outline" size="sm" onClick={retry}>
          {data.failed > 0 ? t("retryFailed") : t("retry")}
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
    </div>
  );
}
