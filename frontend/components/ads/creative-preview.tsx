"use client";

import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import type { CreativeRow } from "@/lib/ads";

export type PreviewItem = { creative: CreativeRow; url: string };

/**
 * Vista previa grande de las imágenes generadas: la imagen al tamaño de la pantalla. Flechas del
 * teclado o botones para recorrer las del lote; Esc o clic fuera para cerrar.
 */
export function CreativePreview({
  items,
  index,
  onIndex,
  onClose,
}: {
  items: PreviewItem[];
  index: number;
  onIndex: (next: number) => void;
  onClose: () => void;
}) {
  const t = useTranslations("ads.batch.preview");
  const tf = useTranslations("ads.wizard.formats");
  const closeRef = useRef<HTMLButtonElement>(null);
  const item = items[index];
  const last = items.length - 1;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden"; // la página de atrás no se desplaza
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight" && index < last) onIndex(index + 1);
      else if (e.key === "ArrowLeft" && index > 0) onIndex(index - 1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [index, last, onIndex, onClose]);

  if (!item) return null;
  const { creative: c, url } = item;
  const label = tf(c.ratio);
  const nav = "flex size-11 shrink-0 items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25 disabled:opacity-30";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("title")}
      className="fixed inset-0 z-[60] flex flex-col bg-black/90 p-3 md:p-6"
      onClick={onClose}
    >
      <div className="flex items-center justify-between gap-3 pb-3 text-white" onClick={(e) => e.stopPropagation()}>
        <div className="min-w-0 text-sm">
          <p className="truncate font-semibold">{c.copy.image.headline}</p>
          <p className="text-white/70">
            {label} · {t("counter", { current: index + 1, total: items.length })}
          </p>
        </div>
        <button ref={closeRef} type="button" onClick={onClose} aria-label={t("close")} className={nav}>
          <X className="size-5" aria-hidden />
        </button>
      </div>

      <div className="flex min-h-0 flex-1 items-center justify-center gap-2 md:gap-4">
        <button
          type="button"
          aria-label={t("previous")}
          className={nav}
          disabled={index === 0}
          onClick={(e) => {
            e.stopPropagation();
            onIndex(index - 1);
          }}
        >
          <ChevronLeft className="size-6" aria-hidden />
        </button>
        {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada temporal de Storage */}
        <img
          src={url}
          alt={`${c.copy.image.headline} (${label})`}
          className="max-h-[calc(100dvh-7rem)] min-w-0 max-w-full rounded-lg object-contain shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        />
        <button
          type="button"
          aria-label={t("next")}
          className={nav}
          disabled={index === last}
          onClick={(e) => {
            e.stopPropagation();
            onIndex(index + 1);
          }}
        >
          <ChevronRight className="size-6" aria-hidden />
        </button>
      </div>
    </div>
  );
}
