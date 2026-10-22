"use client";

import { Link2, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { looksLikeUrl, MAX_PASTED_TEXT, MIN_PASTED_TEXT, normalizeUrl, referenceHost } from "@/lib/reference";
import type { Market, ReferenceResult, SalesReference } from "@/lib/types";

/**
 * Página de ventas de referencia (opcional): se lee la URL, se resume (público, dolores, promesa,
 * tono y ángulo) y ese resumen inspira los problemas y todo el paquete. El contenido es original.
 */
export function ReferencePanel({
  market,
  value,
  onChange,
}: {
  market: Market;
  value: SalesReference | null;
  onChange: (reference: SalesReference | null, result?: ReferenceResult) => void;
}) {
  const t = useTranslations("wizard.reference");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [pasting, setPasting] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notSales, setNotSales] = useState(false);
  const [truncated, setTruncated] = useState(false);

  const analyze = async () => {
    setError(null);
    setPending(true);
    try {
      const result = await api.analyzeReference(
        pasting ? { market, text: text.trim() } : { market, url: normalizeUrl(url) },
      );
      setNotSales(!result.looks_like_sales_page);
      setTruncated(result.page.truncated);
      onChange(result.reference, result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errorGeneric"));
    } finally {
      setPending(false);
    }
  };

  const remove = () => {
    setUrl("");
    setText("");
    setNotSales(false);
    setTruncated(false);
    setError(null);
    onChange(null);
  };

  const canAnalyze = pasting ? text.trim().length >= MIN_PASTED_TEXT : looksLikeUrl(url);
  const host = value ? referenceHost(value) : null;

  return (
    <section className="flex max-w-2xl flex-col gap-3 rounded-xl border p-4" aria-label={t("title")}>
      <div className="flex items-start gap-2">
        <Link2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div>
          <h3 className="font-medium">{t("title")}</h3>
          <p className="text-sm text-muted-foreground">{t("hint")}</p>
        </div>
      </div>

      {!value && (
        <div className="flex flex-col gap-3">
          {pasting ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="reference-text">{t("textLabel")}</Label>
              <Textarea
                id="reference-text"
                rows={6}
                maxLength={MAX_PASTED_TEXT}
                placeholder={t("textPlaceholder")}
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={pending}
              />
              <span className="text-xs text-muted-foreground">{t("textHint", { min: MIN_PASTED_TEXT })}</span>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="reference-url">{t("urlLabel")}</Label>
              <Input
                id="reference-url"
                inputMode="url"
                maxLength={2000}
                placeholder={t("urlPlaceholder")}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && canAnalyze && !pending && void analyze()}
                disabled={pending}
              />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" variant="outline" size="sm" onClick={analyze} disabled={!canAnalyze || pending}>
              {pending ? t("analyzing") : pasting ? t("analyzeText") : t("analyze")}
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
          {!pasting && <span className="text-muted-foreground"> {t("errorTip")}</span>}
        </p>
      )}

      {value && (
        <div className="flex flex-col gap-3 rounded-lg bg-muted/40 p-3 text-sm" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">
              {t("based")}
              {host ? <span className="text-muted-foreground"> · {host}</span> : <span className="text-muted-foreground"> · {t("pastedText")}</span>}
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={remove}>
              <Trash2 className="size-4" aria-hidden />
              {t("remove")}
            </Button>
          </div>
          {notSales && <p className="text-amber-700 dark:text-amber-400">{t("notSales")}</p>}
          {truncated && <p className="text-xs text-muted-foreground">{t("truncated")}</p>}
          <dl className="grid gap-2 sm:grid-cols-[8rem_1fr]">
            <Row label={t("fields.audience")} value={value.audience} />
            <Row label={t("fields.mainPain")} value={value.main_pain} />
            <Row label={t("fields.promise")} value={value.promise} />
            <Row label={t("fields.angle")} value={value.angle} />
            <Row label={t("fields.tone")} value={value.tone} />
            {value.pains.length > 0 && (
              <>
                <dt className="text-muted-foreground">{t("fields.pains")}</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {value.pains.slice(0, 5).map((p) => (
                    <Badge key={p} variant="secondary" className="h-auto whitespace-normal py-0.5 font-normal">
                      {p}
                    </Badge>
                  ))}
                </dd>
              </>
            )}
          </dl>
          <p className="text-xs text-muted-foreground">{t("original")}</p>
        </div>
      )}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </>
  );
}
