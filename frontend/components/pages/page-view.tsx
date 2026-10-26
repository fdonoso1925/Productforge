"use client";

import { Copy, Download, ExternalLink, Monitor, Pencil, RefreshCw, Smartphone, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { ConfirmButton } from "@/components/product/confirm-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError, api } from "@/lib/api";
import { isCheckoutUrl, lovableUrl, type PageContent, type PageRow, previewDocument, type SimilarityReport } from "@/lib/pages";
import { createClient } from "@/lib/supabase/client";
import type { TemplateInfo } from "@/lib/types";
import { ContentEditor } from "./content-editor";

const POLL_MS = 3000;
const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";

function message(e: unknown): string {
  if (e instanceof ApiError) return e.errors.length ? e.errors.join(" · ") : e.message;
  return e instanceof Error ? e.message : String(e);
}

function download(html: string, filename: string, type = "text/html") {
  const url = URL.createObjectURL(new Blob([html], { type: `${type};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Una página de ventas: vista previa, aviso de parecido, edición de textos, exportación. */
export function PageView({ pageId }: { pageId: string }) {
  const t = useTranslations("pages.view");
  const ts = useTranslations("pages.similarity");
  const tc = useTranslations("common");
  const router = useRouter();
  const [page, setPage] = useState<PageRow | null>(null);
  const [working, setWorking] = useState(false);
  const [html, setHtml] = useState<string | null>(null);
  const [device, setDevice] = useState<"mobile" | "desktop">("mobile");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<PageContent | null>(null);
  const [checkout, setCheckout] = useState("");
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [report, setReport] = useState<SimilarityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const load = useCallback(async () => {
    const { data, error: failure } = await createClient().from("sales_pages").select("*").eq("id", pageId).single();
    if (failure) throw new Error(failure.message);
    const row = data as PageRow;
    setPage(row);
    setReport(row.similarity);
    setCheckout((c) => c || row.checkout_url || "");
    return row;
  }, [pageId]);

  // Mientras la IA escribe, se consulta cada pocos segundos; al terminar se carga el resultado.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const [row, state] = await Promise.all([load(), api.pagesState(pageId)]);
        if (!alive) return;
        setWorking(state.working);
        if (state.working || row.status === "planning") timer = setTimeout(tick, POLL_MS);
      } catch (e) {
        if (alive) setError(message(e));
      }
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [load, pageId, nonce]);

  useEffect(() => {
    void api.templates().then(setTemplates).catch(() => undefined);
  }, []);

  const version = page ? `${page.status}|${page.updated_at}` : "";
  useEffect(() => {
    if (!page?.content) return;
    let alive = true;
    api
      .pagesHtml(pageId)
      .then((r) => alive && setHtml(r.html))
      .catch((e) => alive && setError(message(e)));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageId, version]);

  const run = async (action: () => Promise<unknown>, done?: string) => {
    setError(null);
    setNotice(null);
    try {
      await action();
      if (done) setNotice(done);
      await load();
    } catch (e) {
      setError(message(e));
    }
  };

  if (!page) return error ? <ErrorBox message={error} /> : <Loading text={tc("loading")} />;

  const level = report?.level ?? "ok";
  const generating = page.status === "planning" || working;
  const blocked = level === "block";
  const checkoutOk = !checkout.trim() || isCheckoutUrl(checkout);

  const saveContent = () =>
    run(async () => {
      if (!draft) return;
      const result = await api.pagesEdit(pageId, { content: draft });
      setReport(result.similarity);
      setEditing(false);
      setDraft(null);
    }, t("saved"));

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-5 py-4 md:py-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold">{page.title}</h1>
          <p className="text-sm text-muted-foreground">
            {page.reference ? t("modeled") : t("original")}
            {page.reference?.source_url ? ` · ${new URL(page.reference.source_url).host}` : ""}
          </p>
        </div>
        <Link href="/pages" className="text-sm text-muted-foreground hover:underline">
          {t("back")}
        </Link>
      </header>

      {error && <ErrorBox message={error} />}
      {notice && (
        <p role="status" className="text-sm text-emerald-600">
          {notice}
        </p>
      )}

      {generating && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
          <span className="size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-hidden />
          {t("writing")}
        </p>
      )}

      {page.status === "error" && !generating && (
        <div className="flex flex-col gap-2 rounded-xl border border-destructive/40 p-4 text-sm">
          <p className="font-medium text-destructive">{t("failed")}</p>
          {page.error && <p className="text-muted-foreground">{page.error}</p>}
          <div>
            <ConfirmButton label={t("retry")} confirmLabel={t("confirmAi")} onConfirm={() => void run(async () => { await api.pagesRegenerate(pageId); setNonce((n) => n + 1); })} />
          </div>
        </div>
      )}

      {level !== "ok" && report && (
        <section
          role="alert"
          className={`flex flex-col gap-2 rounded-xl border p-4 text-sm ${blocked ? "border-destructive/50 bg-destructive/5" : "border-amber-500/50 bg-amber-500/5"}`}
        >
          <h2 className="font-semibold">{ts(`${level}.title`)}</h2>
          <p>{ts(`${level}.text`)}</p>
          {report.brands.length > 0 && <p>{ts("brands", { names: report.brands.join(", ") })}</p>}
          {report.fields.length > 0 && (
            <p className="text-muted-foreground">{ts("where", { fields: report.fields.slice(0, 5).map((f) => f.path).join(", ") })}</p>
          )}
        </section>
      )}

      {page.content && (
        <>
          <section className="flex flex-wrap items-end gap-3 rounded-xl border p-4">
            <div className="flex min-w-60 flex-1 flex-col gap-1">
              <Label htmlFor="pv-checkout">{t("checkout")}</Label>
              <Input id="pv-checkout" type="url" inputMode="url" placeholder="https://" value={checkout} onChange={(e) => setCheckout(e.target.value)} />
              <p className={`text-xs ${checkoutOk ? "text-muted-foreground" : "text-destructive"}`}>{checkoutOk ? t("checkoutHint") : t("checkoutInvalid")}</p>
            </div>
            {templates.length > 0 && (
              <div className="flex min-w-48 flex-col gap-1">
                <Label htmlFor="pv-template">{t("template")}</Label>
                <select
                  id="pv-template"
                  value={page.template_id}
                  onChange={(e) => void run(() => api.pagesEdit(pageId, { template_id: e.target.value }))}
                  className={SELECT_CLASS}
                >
                  {templates.map((tpl) => (
                    <option key={tpl.id} value={tpl.id}>
                      {tpl.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={!checkoutOk || checkout.trim() === (page.checkout_url ?? "")}
              onClick={() => void run(() => api.pagesEdit(pageId, { checkout_url: checkout.trim() }), t("saved"))}
            >
              {t("saveLink")}
            </Button>
          </section>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={blocked || generating || editing}
              onClick={() => void run(async () => {
                const out = await api.pagesExport(pageId);
                download(out.html, out.filename);
              })}
            >
              <Download aria-hidden />
              {t("download")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={blocked || generating || editing}
              onClick={() => void run(async () => {
                const out = await api.pagesExport(pageId);
                await navigator.clipboard.writeText(out.html);
              }, t("copied"))}
            >
              <Copy aria-hidden />
              {t("copy")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={blocked || generating || editing}
              onClick={() =>
                void run(async () => {
                  const out = await api.pagesLovable(pageId);
                  await navigator.clipboard.writeText(out.prompt).catch(() => undefined);
                  // Con textos muy largos el enlace puede fallar: se abre Lovable vacío y se pega.
                  window.open(out.link_ok ? lovableUrl(out.prompt) : "https://lovable.dev/", "_blank", "noopener,noreferrer");
                }, t("lovableDone"))
              }
            >
              <ExternalLink aria-hidden />
              {t("lovable")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={blocked || generating || editing}
              onClick={() =>
                void run(async () => {
                  await navigator.clipboard.writeText((await api.pagesLovable(pageId)).prompt);
                }, t("promptCopied"))
              }
            >
              <Copy aria-hidden />
              {t("copyPrompt")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={blocked || generating || editing}
              onClick={() =>
                void run(async () => {
                  const out = await api.pagesLovable(pageId);
                  download(out.prompt, `prompt-lovable-${page.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40)}.txt`, "text/plain");
                })
              }
            >
              <Download aria-hidden />
              {t("downloadPrompt")}
            </Button>
            <Button
              variant={editing ? "default" : "outline"}
              size="sm"
              disabled={generating}
              onClick={() => {
                setEditing((e) => !e);
                setDraft(editing ? null : (page.content as PageContent));
              }}
            >
              <Pencil aria-hidden />
              {editing ? t("cancelEdit") : t("edit")}
            </Button>
            <ConfirmButton
              label={t("regenerate")}
              confirmLabel={t("confirmAi")}
              disabled={generating}
              icon={<RefreshCw aria-hidden />}
              onConfirm={() => void run(async () => { await api.pagesRegenerate(pageId); setNonce((n) => n + 1); })}
            />
            <ConfirmButton
              label={t("delete")}
              confirmLabel={t("confirmDelete")}
              icon={<Trash2 aria-hidden />}
              onConfirm={() => void run(async () => { await api.pagesDelete(pageId); router.push("/pages"); })}
            />
          </div>
          {blocked && <p className="text-xs text-destructive">{t("exportBlocked")}</p>}
          <p className="text-xs text-muted-foreground">{t("lovableHint")}</p>

          {editing && draft ? (
            <section className="flex flex-col gap-4">
              <ContentEditor content={draft} similarity={report} onChange={setDraft} />
              <div className="sticky bottom-24 flex gap-2 md:bottom-4">
                <Button onClick={() => void saveContent()}>{t("saveText")}</Button>
              </div>
            </section>
          ) : (
            <section className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">{t("preview")}</h2>
                <div className="flex gap-1" role="group" aria-label={t("device")}>
                  <Button variant={device === "mobile" ? "default" : "outline"} size="icon-sm" aria-label={t("mobile")} aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}>
                    <Smartphone aria-hidden />
                  </Button>
                  <Button variant={device === "desktop" ? "default" : "outline"} size="icon-sm" aria-label={t("desktop")} aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}>
                    <Monitor aria-hidden />
                  </Button>
                </div>
              </div>
              {html ? (
                <iframe
                  title={t("preview")}
                  sandbox="allow-popups allow-popups-to-escape-sandbox"
                  srcDoc={previewDocument(html)}
                  className={`mx-auto h-[720px] w-full rounded-xl border bg-white ${device === "mobile" ? "max-w-[390px]" : ""}`}
                />
              ) : (
                <Loading text={tc("loading")} />
              )}
              <p className="text-xs text-muted-foreground">{t("previewNote")}</p>
            </section>
          )}
        </>
      )}

      {page.reference && (
        <section className="flex flex-col gap-2 rounded-xl border p-4 text-sm">
          <h2 className="font-semibold">{t("beatTitle")}</h2>
          <p className="text-muted-foreground">{t("beatHint")}</p>
          {[
            [t("weaknesses"), page.reference.weaknesses],
            [t("missing"), page.reference.missing],
          ].map(([title, items]) =>
            (items as string[]).length > 0 ? (
              <div key={title as string}>
                <strong>{title as string}</strong>
                <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                  {(items as string[]).map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              </div>
            ) : null,
          )}
        </section>
      )}
    </main>
  );
}
