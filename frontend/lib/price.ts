import type { Market } from "@/lib/types";

// Precio de venta + precio normal («de R$ 97 por R$ 47»). Lo escribe el usuario; aquí solo se
// arma el texto que viaja al backend (`price_text` / `base_price_text`), que lo usa tal cual en los
// anuncios y en la página de ventas y vuelve a validarlo (app/pricing.py).

export const CURRENCIES = ["BRL", "USD"] as const;
export type Currency = (typeof CURRENCIES)[number];
export type PriceInput = { currency: Currency; price: string; base: string };

/** Reales para Brasil (pt-BR); dólares para el resto. */
export function defaultCurrency(market: Market): Currency {
  return market === "pt-BR" ? "BRL" : "USD";
}

export function emptyPrice(market: Market): PriceInput {
  return { currency: defaultCurrency(market), price: "", base: "" };
}

/** Al cambiar de mercado, la moneda sigue al mercado mientras no se haya escrito un precio. */
export function forMarket(input: PriceInput, market: Market): PriceInput {
  return input.price.trim() || input.base.trim() ? input : emptyPrice(market);
}

/** «47», «47,90» o «47.90» → 47.9; vacío o inválido → null. */
export function parseAmount(raw: string): number | null {
  const clean = raw.trim().replace(/\s/g, "");
  if (!clean) return null;
  const lastDot = clean.lastIndexOf(".");
  const lastComma = clean.lastIndexOf(",");
  let normalized = clean;
  if (lastDot >= 0 && lastComma >= 0) {
    const decimal = lastComma > lastDot ? "," : ".";
    normalized = clean
      .replaceAll(decimal === "," ? "." : ",", "")
      .replace(decimal, ".");
  } else if (lastComma >= 0) {
    normalized =
      clean.length - lastComma - 1 <= 2
        ? clean.replace(",", ".")
        : clean.replaceAll(",", "");
  } else if (lastDot >= 0 && clean.length - lastDot - 1 === 3) {
    normalized = clean.replaceAll(".", ""); // «1.000» = mil
  }
  const value = Number(normalized);
  return Number.isFinite(value) && value > 0 ? value : null;
}

/** «R$ 47», «R$ 47,90», «US$ 19.90» (sin decimales si son redondos). */
export function formatMoney(value: number, currency: Currency): string {
  const cents = Math.round(value * 100) % 100 !== 0;
  const digits = {
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: 2,
  };
  return currency === "BRL"
    ? `R$ ${value.toLocaleString("pt-BR", digits)}`
    : `US$ ${value.toLocaleString("en-US", digits)}`;
}

export function savingsPct(
  base: number | null,
  price: number | null,
): number | null {
  if (!base || !price || price >= base) return null;
  return Math.round((1 - price / base) * 100);
}

export type PriceCheck =
  "ok" | "baseWithoutPrice" | "baseNotHigher" | "invalid";

export function checkPrice(input: PriceInput): PriceCheck {
  const price = parseAmount(input.price);
  const base = parseAmount(input.base);
  if (
    (input.price.trim() && price === null) ||
    (input.base.trim() && base === null)
  )
    return "invalid";
  if (base !== null && price === null) return "baseWithoutPrice";
  if (base !== null && price !== null && price >= base) return "baseNotHigher";
  return "ok";
}

/** Los textos que viajan al backend (vacíos si no hay precio). */
export function priceTexts(input: PriceInput): {
  price_text: string;
  base_price_text: string;
} {
  const price = parseAmount(input.price);
  const base = parseAmount(input.base);
  if (price === null) return { price_text: "", base_price_text: "" };
  return {
    price_text: formatMoney(price, input.currency),
    base_price_text:
      base !== null && base > price ? formatMoney(base, input.currency) : "",
  };
}
