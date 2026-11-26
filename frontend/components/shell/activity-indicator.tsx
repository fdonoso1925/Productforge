"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState, useSyncExternalStore } from "react";
import { activeCount, subscribe } from "@/lib/activity";

const SHOW_AFTER_MS = 200; // lo instantáneo no parpadea

/**
 * Barra fina arriba y aviso «Procesando…» abajo mientras haya alguna acción en curso con el
 * backend. Se monta una vez en el marco de la app.
 */
export function ActivityIndicator() {
  const t = useTranslations("common");
  const count = useSyncExternalStore(subscribe, activeCount, () => 0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (count === 0) {
      const off = setTimeout(() => setVisible(false), 0);
      return () => clearTimeout(off);
    }
    const on = setTimeout(() => setVisible(true), SHOW_AFTER_MS);
    return () => clearTimeout(on);
  }, [count]);

  if (!visible) return null;
  return (
    <>
      <div className="activity-bar fixed inset-x-0 top-0 z-[60] h-[3px] overflow-hidden" aria-hidden>
        <span />
      </div>
      <div
        role="status"
        aria-live="polite"
        className="fixed right-4 bottom-[100px] z-[60] flex items-center gap-2 rounded-full border bg-popover/95 px-4 py-2 text-sm font-semibold shadow-xl backdrop-blur md:bottom-5"
      >
        <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-hidden />
        {t("processing")}
      </div>
    </>
  );
}
