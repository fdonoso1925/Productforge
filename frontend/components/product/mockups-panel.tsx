"use client";

import { Download, Images } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorBox } from "@/components/wizard/step-nav";
import { ApiError, api } from "@/lib/api";

const KINDS = ["book", "tablet", "phone", "bundle"] as const;

/**
 * Mockups de la portada (libro, tablet, celular y pack) como PNG transparentes para anuncios,
 * redes o la página de ventas. Se dibujan al pedirlos, con la portada real del producto.
 */
export function MockupsPanel({ productId }: { productId: string }) {
  const t = useTranslations("product.mockups");
  const [urls, setUrls] = useState<Record<string, string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const make = async () => {
    setBusy(true);
    setError(null);
    try {
      setUrls((await api.productMockups(productId)).urls);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass flex flex-col gap-4 rounded-[20px] p-4" aria-label={t("title")}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex max-w-xl flex-col gap-1">
          <h2 className="flex items-center gap-2 font-semibold">
            <Images className="size-4" aria-hidden />
            {t("title")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("hint")}</p>
        </div>
        <Button variant={urls ? "outline" : "default"} onClick={() => void make()} disabled={busy}>
          {busy ? t("making") : urls ? t("remake") : t("cta")}
        </Button>
      </div>
      {error && <ErrorBox message={error} />}
      {urls && (
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {KINDS.map((kind) => (
            <li key={kind} className="flex flex-col gap-2 rounded-[16px] bg-white/5 p-3">
              {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada de Storage, cambia cada vez */}
              <img src={urls[kind]} alt={t(`kinds.${kind}`)} className="aspect-square w-full object-contain" />
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">{t(`kinds.${kind}`)}</span>
                <a
                  href={urls[kind]}
                  download={`mockup-${kind}.png`}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={t("download", { kind: t(`kinds.${kind}`) })}
                  className="inline-flex size-8 items-center justify-center rounded-lg border hover:bg-white/10"
                >
                  <Download className="size-4" aria-hidden />
                </a>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
