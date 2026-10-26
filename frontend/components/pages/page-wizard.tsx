"use client";

import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { ConfirmButton } from "@/components/product/confirm-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError, api } from "@/lib/api";
import { isCheckoutUrl, type PageBriefPreview, type TeardownResult } from "@/lib/pages";
import { createClient } from "@/lib/supabase/client";
import type { Market, TemplateInfo } from "@/lib/types";
import { ModelPanel } from "./model-panel";

const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";

type ProductOption = { id: string; niche: string; market: Market; outline: { product_name?: string } | null };

function message(e: unknown): string {
  if (e instanceof ApiError) return e.errors.length ? e.errors.join(" · ") : e.message;
  return e instanceof Error ? e.message : String(e);
}

/** Crear una página de ventas: desde un paquete hecho o a mano, y opcionalmente modelada sobre otra. */
export function PageWizard({ productId }: { productId?: string }) {
  const t = useTranslations("pages.wizard");
  const tc = useTranslations("common");
  const tm = useTranslations("markets");
  const router = useRouter();
  const [products, setProducts] = useState<ProductOption[] | null>(null);
  const [source, setSource] = useState<string>(productId ?? "");
  const [loaded, setLoaded] = useState<{ id: string; data: PageBriefPreview } | null>(null);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [template, setTemplate] = useState("");
  const [manual, setManual] = useState({ niche: "", product_name: "", problem: "", audience: "", promise: "", timeframe: "" });
  const [market, setMarket] = useState<Market>("es-LATAM");
  const [form, setForm] = useState({ price: "", guarantee: "", urgency: "", about: "", checkout: "" });
  const [proofs, setProofs] = useState<string[]>([]);
  const [model, setModel] = useState<TeardownResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let alive = true;
    void createClient()
      .from("products")
      .select("id, niche, market, outline")
      .eq("status", "ready")
      .order("created_at", { ascending: false })
      .limit(100)
      .then(({ data, error: failure }) => {
        if (!alive) return;
        if (failure) setError(failure.message);
        else setProducts((data ?? []) as ProductOption[]);
      });
    void api.templates().then((list) => alive && setTemplates(list)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!source) return;
    let alive = true;
    api
      .pagesBrief(source)
      .then((p) => {
        if (!alive) return;
        setLoaded({ id: source, data: p });
        setTemplate(p.template_id);
        setProofs(p.proofs.map((x) => x.id));
        setMarket(p.brief.market);
      })
      .catch((e) => alive && setError(message(e)));
    return () => {
      alive = false;
    };
  }, [source]);

  // El resumen del paquete solo vale mientras siga elegido ese paquete.
  const preview = loaded && loaded.id === source ? loaded.data : null;

  // Un cambio de mercado descarta el análisis: se hizo en el idioma anterior.
  const changeMarket = (next: Market) => {
    setMarket(next);
    setModel(null);
  };

  const manualOk = useMemo(
    () => manual.niche.trim().length >= 2 && manual.product_name.trim() && manual.problem.trim().length >= 3 && manual.audience.trim().length >= 3 && manual.promise.trim().length >= 3,
    [manual],
  );
  const checkoutOk = !form.checkout.trim() || isCheckoutUrl(form.checkout);
  const ready = (source ? preview !== null : Boolean(manualOk)) && checkoutOk;

  const submit = async () => {
    setPending(true);
    setError(null);
    try {
      const { page_id } = await api.pagesCreate({
        market,
        ...(source ? { product_id: source } : { manual: { ...manual, timeframe: manual.timeframe.trim() } }),
        ...(template ? { template_id: template } : {}),
        ...(form.checkout.trim() ? { checkout_url: form.checkout.trim() } : {}),
        price_text: form.price.trim(),
        guarantee_text: form.guarantee.trim(),
        real_urgency: form.urgency.trim(),
        about_author: form.about.trim(),
        proof_ids: source ? proofs : [],
        ...(model ? { reference: model.reference, fingerprint: model.fingerprint } : {}),
      });
      router.push(`/pages/${page_id}`);
    } catch (e) {
      setError(message(e));
      setPending(false);
    }
  };

  const field = (id: keyof typeof form, label: string, hint: string, multiline = false) => (
    <div className="flex flex-col gap-1">
      <Label htmlFor={`pw-${id}`}>{label}</Label>
      {multiline ? (
        <Textarea id={`pw-${id}`} rows={3} value={form[id]} onChange={(e) => setForm({ ...form, [id]: e.target.value })} />
      ) : (
        <Input id={`pw-${id}`} value={form[id]} onChange={(e) => setForm({ ...form, [id]: e.target.value })} />
      )}
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("hint")}</p>
        </div>
        <Link href="/pages" className="text-sm text-muted-foreground hover:underline">
          {t("back")}
        </Link>
      </header>

      <section className="flex flex-col gap-3 rounded-xl border p-4">
        <h2 className="font-semibold">{t("sourceTitle")}</h2>
        {!products && !error && <Loading text={tc("loading")} />}
        {products && (
          <div className="flex flex-col gap-1">
            <Label htmlFor="pw-source">{t("sourceLabel")}</Label>
            <select id="pw-source" value={source} onChange={(e) => setSource(e.target.value)} className={SELECT_CLASS}>
              <option value="">{t("sourceManual")}</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.outline?.product_name ?? p.niche} · {tm(p.market)}
                </option>
              ))}
            </select>
          </div>
        )}
        {source && !preview && !error && <Loading text={tc("loading")} />}
        {source && preview && (
          <dl className="grid gap-1 text-sm sm:grid-cols-[8rem_1fr]">
            <dt className="text-muted-foreground">{t("product")}</dt>
            <dd className="font-medium">{preview.brief.product_name}</dd>
            <dt className="text-muted-foreground">{t("audience")}</dt>
            <dd>{preview.brief.audience}</dd>
            <dt className="text-muted-foreground">{t("promise")}</dt>
            <dd>{preview.brief.promise}</dd>
            <dt className="text-muted-foreground">{t("pieces")}</dt>
            <dd>{preview.brief.deliverables.map((d) => d.title).join(" · ")}</dd>
          </dl>
        )}
        {!source && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="pw-market">{t("market")}</Label>
              <select id="pw-market" value={market} onChange={(e) => changeMarket(e.target.value as Market)} className={SELECT_CLASS}>
                <option value="es-LATAM">{tm("es-LATAM")}</option>
                <option value="pt-BR">{tm("pt-BR")}</option>
              </select>
            </div>
            {(
              [
                ["product_name", t("manual.name")],
                ["niche", t("manual.niche")],
                ["audience", t("manual.audience")],
                ["problem", t("manual.problem")],
                ["promise", t("manual.promise")],
                ["timeframe", t("manual.timeframe")],
              ] as const
            ).map(([key, label]) => (
              <div key={key} className="flex flex-col gap-1">
                <Label htmlFor={`pw-m-${key}`}>{label}</Label>
                <Input id={`pw-m-${key}`} value={manual[key]} onChange={(e) => setManual({ ...manual, [key]: e.target.value })} />
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-4 rounded-xl border p-4">
        <div>
          <h2 className="font-semibold">{t("offerTitle")}</h2>
          <p className="text-sm text-muted-foreground">{t("offerHint")}</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {field("price", t("price"), t("priceHint"))}
          {field("urgency", t("urgency"), t("urgencyHint"))}
        </div>
        {field("guarantee", t("guarantee"), t("guaranteeHint"), true)}
        {field("about", t("about"), t("aboutHint"), true)}
        <div className="flex flex-col gap-1">
          <Label htmlFor="pw-checkout">{t("checkout")}</Label>
          <Input id="pw-checkout" type="url" inputMode="url" placeholder="https://" value={form.checkout} onChange={(e) => setForm({ ...form, checkout: e.target.value })} />
          <p className={`text-xs ${checkoutOk ? "text-muted-foreground" : "text-destructive"}`}>{checkoutOk ? t("checkoutHint") : t("checkoutInvalid")}</p>
        </div>
        {templates.length > 0 && (
          <div className="flex flex-col gap-1">
            <Label htmlFor="pw-template">{t("template")}</Label>
            <select id="pw-template" value={template} onChange={(e) => setTemplate(e.target.value)} className={SELECT_CLASS}>
              {!template && <option value="">{t("templateDefault")}</option>}
              {templates.map((tpl) => (
                <option key={tpl.id} value={tpl.id}>
                  {tpl.name}
                </option>
              ))}
            </select>
          </div>
        )}
        {source && preview && preview.proofs.length > 0 && (
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">{t("proofs")}</legend>
            <p className="text-xs text-muted-foreground">{t("proofsHint")}</p>
            {preview.proofs.map((p) => (
              <label key={p.id} className="flex cursor-pointer items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={proofs.includes(p.id)}
                  onChange={(e) => setProofs(e.target.checked ? [...proofs, p.id] : proofs.filter((x) => x !== p.id))}
                />
                <span>
                  {p.text}
                  {p.author && <span className="text-muted-foreground"> — {p.author}</span>}
                </span>
              </label>
            ))}
          </fieldset>
        )}
      </section>

      <ModelPanel market={market} value={model} onChange={setModel} />

      {error && <ErrorBox message={error} />}
      <div className="flex flex-wrap items-center gap-3">
        <ConfirmButton
          size="default"
          label={t("create")}
          confirmLabel={t("confirm")}
          onConfirm={() => void submit()}
          disabled={!ready || pending}
          icon={<Sparkles aria-hidden />}
        />
        <p className="text-xs text-muted-foreground">{t("createHint")}</p>
      </div>
    </main>
  );
}
