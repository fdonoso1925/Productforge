"use client";

import { Cloud } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmButton } from "@/components/product/confirm-button";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { ApiError, api } from "@/lib/api";
import type { DriveStatus } from "@/lib/types";

export type Outcome = "connected" | "denied" | "error" | null;

export function DriveCard({ outcome }: { outcome: Outcome }) {
  const t = useTranslations("settings.drive");
  const locale = useLocale() as "es" | "pt";
  const [status, setStatus] = useState<DriveStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [queued, setQueued] = useState<number | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api.driveStatus().then(
      (s) => setStatus(s),
      (e) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, [reload]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const connect = () =>
    run(async () => {
      const { url } = await api.driveConnect(locale);
      // Google pide el permiso y devuelve al usuario a /settings?drive=…
      window.location.assign(url);
      await new Promise(() => {}); // la página se va: mantiene el botón ocupado
    });

  const disconnect = () =>
    run(async () => {
      await api.driveDisconnect();
      setQueued(null);
      setReload((n) => n + 1);
    });

  const syncAll = () =>
    run(async () => {
      const { products } = await api.driveSyncAll();
      setQueued(products);
    });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cloud className="size-5" aria-hidden />
          {t("title")}
          {status?.connected && <Badge>{t("connectedNoName")}</Badge>}
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {outcome && (
          <p
            role={outcome === "connected" ? "status" : "alert"}
            className={`rounded-lg p-3 text-sm ${outcome === "connected" ? "bg-primary/10" : "bg-destructive/10 text-destructive"}`}
          >
            {t(`outcome.${outcome}`)}
          </p>
        )}
        {error && <ErrorBox message={error} />}
        {!status && !error && <Loading text="…" />}

        {status && !status.configured && <p className="text-sm text-muted-foreground">{t("notConfigured")}</p>}

        {status?.configured && !status.connected && (
          <div className="flex flex-col items-start gap-3">
            <p className="text-sm text-muted-foreground">{t("folderHint")}</p>
            <Button onClick={connect} disabled={busy}>
              {busy ? t("connecting") : t("connect")}
            </Button>
          </div>
        )}

        {status?.connected && (
          <div className="flex flex-col gap-4">
            <p className="text-sm">
              {status.account ? t("connected", { account: status.account }) : t("connectedNoName")}
            </p>
            <p className="text-sm text-muted-foreground">{t("folderHint")}</p>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={syncAll} disabled={busy}>
                {t("syncAll")}
              </Button>
              <ConfirmButton
                label={t("disconnect")}
                confirmLabel={t("disconnectConfirm")}
                onConfirm={disconnect}
                disabled={busy}
              />
              {queued !== null && (
                <span className="text-sm text-muted-foreground" aria-live="polite">
                  {t("queued", { count: queued })}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{t("disconnectHint")}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
