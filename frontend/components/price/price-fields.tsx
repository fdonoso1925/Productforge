"use client";

import { useTranslations } from "next-intl";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CURRENCIES,
  checkPrice,
  formatMoney,
  parseAmount,
  savingsPct,
  type Currency,
  type PriceInput,
} from "@/lib/price";

const SELECT =
  "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";

/**
 * Precio de venta y precio normal opcional, con su moneda (reales o dólares). Muestra cómo se
 * verá («De R$ 97 por R$ 47 · −52 %»). Solo precios reales: el anuncio y la página los usan tal cual.
 */
export function PriceFields({
  id,
  value,
  onChange,
}: {
  id: string;
  value: PriceInput;
  onChange: (next: PriceInput) => void;
}) {
  const t = useTranslations("price");
  const check = checkPrice(value);
  const price = parseAmount(value.price);
  const base = parseAmount(value.base);
  const pct = savingsPct(base, price);

  return (
    <div className="flex flex-col gap-2 sm:col-span-2">
      <div className="grid gap-3 sm:grid-cols-[140px_1fr_1fr]">
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-currency`}>{t("currency")}</Label>
          <select
            id={`${id}-currency`}
            value={value.currency}
            onChange={(e) =>
              onChange({ ...value, currency: e.target.value as Currency })
            }
            className={SELECT}
          >
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {t(`currencies.${c}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-price`}>{t("price")}</Label>
          <Input
            id={`${id}-price`}
            inputMode="decimal"
            value={value.price}
            onChange={(e) => onChange({ ...value, price: e.target.value })}
            placeholder={value.currency === "BRL" ? "47,00" : "19.90"}
            maxLength={12}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-base`}>{t("base")}</Label>
          <Input
            id={`${id}-base`}
            inputMode="decimal"
            value={value.base}
            onChange={(e) => onChange({ ...value, base: e.target.value })}
            placeholder={value.currency === "BRL" ? "97,00" : "49.90"}
            maxLength={12}
          />
        </div>
      </div>
      {check !== "ok" ? (
        <p role="alert" className="text-xs text-destructive">
          {t(`errors.${check}`)}
        </p>
      ) : price !== null ? (
        <p className="text-sm" aria-live="polite">
          {base !== null && pct !== null ? (
            <>
              {t("previewFrom")}{" "}
              <s className="text-muted-foreground">
                {formatMoney(base, value.currency)}
              </s>{" "}
              {t("previewTo")}{" "}
              <strong>{formatMoney(price, value.currency)}</strong>
              <span className="ml-2 rounded-full bg-primary px-2 py-0.5 text-xs font-semibold text-primary-foreground">
                −{pct} %
              </span>
            </>
          ) : (
            <strong>{formatMoney(price, value.currency)}</strong>
          )}
        </p>
      ) : null}
      <p className="text-xs text-muted-foreground">{t("hint")}</p>
    </div>
  );
}
