"use client";

import { Upload } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorBox } from "@/components/wizard/step-nav";
import type { ImportReport } from "@/lib/ads";
import { ApiError, api } from "@/lib/api";

const MAX_BYTES = 2 * 1024 * 1024; // el mismo tope que el backend

/** Importa el informe CSV de Ads Manager; se empareja con los creativos por nombre de archivo. */
export function ImportPanel({ onImported }: { onImported: () => void }) {
  const t = useTranslations("ads.import");
  const input = useRef<HTMLInputElement>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const upload = async (file: File) => {
    setError(null);
    setReport(null);
    if (file.size > MAX_BYTES) return setError(t("tooBig"));
    setPending(true);
    try {
      const result = await api.adsImportResults(file);
      setReport(result);
      if (result.imported > 0) onImported();
    } catch (e) {
      setError(e instanceof ApiError ? (e.errors.length ? e.errors.join(" · ") : e.message) : String(e));
    } finally {
      setPending(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <section className="flex flex-col gap-3 rounded-xl border p-4" aria-label={t("title")}>
      <div>
        <h3 className="font-semibold">{t("title")}</h3>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv,text/plain"
        className="sr-only"
        id="ads-import-file"
        onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])}
      />
      <div>
        <Button variant="outline" onClick={() => input.current?.click()} disabled={pending}>
          <Upload aria-hidden />
          {pending ? t("importing") : t("choose")}
        </Button>
      </div>
      {error && <ErrorBox message={error} />}
      {report && (
        <div className="flex flex-col gap-2 text-sm" aria-live="polite">
          <p className="font-medium">{t("summary", { matched: report.matched, rows: report.rows, imported: report.imported })}</p>
          {report.invalid > 0 && <p className="text-amber-700 dark:text-amber-300">{t("invalid", { count: report.invalid })}</p>}
          {report.ambiguous.length > 0 && (
            <p>
              <strong>{t("ambiguous")}:</strong> {report.ambiguous.join(", ")}
            </p>
          )}
          {report.unmatched.length > 0 && (
            <details>
              <summary className="cursor-pointer">{t("unmatched", { count: report.unmatched.length })}</summary>
              <p className="mt-1 break-words text-muted-foreground">{report.unmatched.join(", ")}</p>
              <p className="mt-1 text-xs text-muted-foreground">{t("unmatchedHint")}</p>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
