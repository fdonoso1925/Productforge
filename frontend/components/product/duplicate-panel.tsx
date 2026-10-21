"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorBox } from "@/components/wizard/step-nav";
import { useRouter } from "@/i18n/navigation";
import { ApiError, api } from "@/lib/api";
import type { Market, ProductRow } from "@/lib/types";
import { ConfirmButton } from "./confirm-button";

export function otherMarket(market: Market): Market {
  return market === "pt-BR" ? "es-LATAM" : "pt-BR";
}

/** Duplica el paquete al otro mercado: una versión adaptada (no traducida) vinculada al original. */
export function DuplicatePanel({ product, onClose }: { product: ProductRow; onClose: () => void }) {
  const t = useTranslations("product.actions");
  const tm = useTranslations("markets");
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const target = otherMarket(product.market);
  const market = tm(target);

  const submit = async () => {
    setPending(true);
    setError(null);
    try {
      const { product_id } = await api.duplicate(product.id, target);
      router.push(`/products/${product_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setPending(false);
    }
  };

  return (
    <section className="flex flex-col gap-4 rounded-xl border bg-muted/30 p-4" aria-label={t("duplicateTitle")}>
      <div>
        <h2 className="font-semibold">{t("duplicateTitle")}</h2>
        <p className="text-sm text-muted-foreground">{t("duplicateHint", { market })}</p>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={onClose} disabled={pending}>
          {t("cancel")}
        </Button>
        <ConfirmButton
          size="default"
          label={t("duplicateConfirm", { market })}
          confirmLabel={t("regenerateConfirm")}
          onConfirm={submit}
          disabled={pending}
        />
      </div>
    </section>
  );
}
