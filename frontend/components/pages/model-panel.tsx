"use client";

import { ScanSearch, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import type { TeardownResult } from "@/lib/pages";
import { looksLikeUrl, MAX_PASTED_TEXT, MIN_PASTED_TEXT, normalizeUrl } from "@/lib/reference";
import type { Market } from "@/lib/types";

/**
 * Página que se toma de modelo (opcional): se lee, se analiza (estructura, qué hace bien, dónde
 * pierde ventas) y la nuestra se escribe desde cero, superándola. De ella no se guarda el texto.
 */
export function ModelPanel({
  market,
  value,
  onChange,
}: {
  market: Market;
  value: TeardownResult | null;
  onChange: (result: TeardownResult | null) => void;
}) {
  const t = useTranslations("pages.model");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [pasting, setPasting] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyze = async () => {
    setError(null);
    setPending(true);
    try {
      onChange(await api.pagesReference(pasting ? { market, text: text.trim() } : { market, url: normalizeUrl(url) }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errorGeneric"));
    } finally {
      setPending(false);
    }
  };

  const canAnalyze = pasting ? text.trim().length >= MIN_PASTED_TEXT : looksLikeUrl(url);
  const ref = value?.reference;

  return (
    <section className="flex flex-col gap-3 rounded-xl border p-4" aria-label={t("title")}>
      <div className="flex items-start gap-2">
        <ScanSearch className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div>
          <h3 className="font-medium">{t("title")}</h3>
          <p className="text-sm text-muted-foreground">{t("hint")}</p>
        </div>
      </div>

      {!value && (
        <div className="flex flex-col gap-3">
          {pasting ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="model-text">{t("textLabel")}</Label>
              <Textarea
                id="model-text"
                rows={6}
                maxLength={MAX_PASTED_TEXT}
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={pending}
              />
              <span className="text-xs text-muted-foreground">{t("textHint", { min: MIN_PASTED_TEXT })}</span>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="model-url">{t("urlLabel")}</Label>
              <Input
                id="model-url"
                inputMode="url"
                maxLength={2000}
                placeholder="https://"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && canAnalyze && !pending && void analyze()}
                disabled={pending}
              />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" variant="outline" size="sm" onClick={analyze} disabled={!canAnalyze || pending}>
              {pending ? t("analyzing") : t("analyze")}
            </Button>
            <button
              type="button"
              className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
              onClick={() => {
                setPasting((p) => !p);
                setError(null);
              }}
              disabled={pending}
            >
              {pasting ? t("useUrl") : t("pasteInstead")}
            </button>
          </div>
          {pending && <p className="text-xs text-muted-foreground">{t("analyzingHint")}</p>}
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {value && ref && (
        <div className="flex flex-col gap-3 rounded-lg bg-muted/40 p-3 text-sm" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">
              {t("analyzed")}
              <span className="text-muted-foreground"> · {ref.source_url ? new URL(ref.source_url).host : t("pasted")}</span>
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setUrl("");
                setText("");
                onChange(null);
              }}
            >
              <Trash2 className="size-4" aria-hidden />
              {t("remove")}
            </Button>
          </div>
          {!value.looks_like_sales_page && <p className="text-amber-700 dark:text-amber-400">{t("notSales")}</p>}
          {ref.structure.length > 0 && (
            <p>
              <strong>{t("structure")}:</strong> {ref.structure.map((s) => s.kind).join(" → ")}
            </p>
          )}
          <List title={t("strengths")} items={ref.strengths} />
          <List title={t("weaknesses")} items={ref.weaknesses} />
          <List title={t("missing")} items={ref.missing} />
          <p className="text-xs text-muted-foreground">{t("original")}</p>
        </div>
      )}
    </section>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <strong>{title}</strong>
      <ul className="mt-1 list-disc pl-5 text-muted-foreground">
        {items.slice(0, 5).map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}
