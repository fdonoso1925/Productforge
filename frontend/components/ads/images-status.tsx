"use client";

import { ImageIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import type { ImageProviderStatus } from "@/lib/ads";
import { api } from "@/lib/api";

const NAMES: Record<string, string> = { pixabay: "Pixabay", gemini: "Gemini" };

const usd = (n: number) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Qué proveedores de fotos están activos hoy y cuánto se gastó (Pixabay es gratis; Gemini cobra). */
export function ImagesStatus() {
  const t = useTranslations("ads.images");
  const [providers, setProviders] = useState<ImageProviderStatus[] | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .adsImagesStatus()
      .then((r) => alive && setProviders(r.providers))
      .catch(() => undefined); // un extra informativo: nunca estorba
    return () => {
      alive = false;
    };
  }, []);

  if (!providers || providers.length === 0) return null;

  const line = (p: ImageProviderStatus) => {
    const name = NAMES[p.name] ?? p.name;
    if (!p.enabled) return t("off", { name });
    if (p.free) return t("free", { name });
    const base = t("paid", { name, spent: usd(p.spent_today_usd), cap: usd(p.daily_cap_usd ?? 0) });
    return p.exhausted ? `${base} · ${t("exhausted")}` : base;
  };

  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      <ImageIcon className="size-3.5" aria-hidden />
      <span>{t("title")}:</span>
      {providers.map((p, i) => (
        <span key={p.name}>
          {i > 0 && "· "}
          {line(p)}
        </span>
      ))}
    </p>
  );
}
