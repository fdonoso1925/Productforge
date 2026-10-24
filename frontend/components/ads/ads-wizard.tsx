"use client";

import { Sparkles, Trophy, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { ConfirmButton } from "@/components/product/confirm-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorBox, Loading, StepNav } from "@/components/wizard/step-nav";
import { Link, useRouter } from "@/i18n/navigation";
import {
  type AdBrief,
  type AngleInfo,
  type AnglePick,
  type AngleSuggestion,
  type Avatar,
  creativeCount,
  draftCount,
  LIMITS,
  lines,
  RATIOS,
  type Ratio,
  validatePicks,
} from "@/lib/ads";
import { ApiError, api, type BriefSource } from "@/lib/api";
import type { Market, TemplateInfo } from "@/lib/types";
import { ProofsPanel } from "./proofs-panel";

export type ProductOption = {
  id: string;
  title: string | null;
  niche: string;
  market: Market;
  template_id: string;
};

const STEPS = ["brief", "avatars", "angles"] as const;
const DEFAULT_TEMPLATE = "minimal-clean";
const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";

function emptyManual(market: Market): AdBrief {
  return {
    market,
    niche: "",
    product_name: "",
    problem: "",
    audience: "",
    promise: "",
    price_text: "",
    bonuses: [],
    real_urgency: "",
  };
}

function message(e: unknown): string {
  if (e instanceof ApiError) return e.errors.length ? `${e.message}: ${e.errors.join(" · ")}` : e.message;
  return e instanceof Error ? e.message : String(e);
}

export function AdsWizard({
  products,
  initialProductId,
  defaultMarket,
}: {
  products: ProductOption[];
  initialProductId?: string;
  defaultMarket: Market;
}) {
  const t = useTranslations("ads.wizard");
  const tc = useTranslations("common");
  const router = useRouter();
  const startsWithProduct = products.some((p) => p.id === initialProductId);

  const [step, setStep] = useState(0);
  const [source, setSource] = useState<"product" | "manual">(
    startsWithProduct || (products.length > 0 && !initialProductId) ? "product" : "manual",
  );
  const [productId, setProductId] = useState(startsWithProduct ? (initialProductId as string) : (products[0]?.id ?? ""));
  const [manual, setManual] = useState<AdBrief>(emptyManual(defaultMarket));
  const [bonusText, setBonusText] = useState("");
  const [price, setPrice] = useState("");
  const [urgency, setUrgency] = useState("");

  const [avatars, setAvatars] = useState<{ key: string; list: Avatar[] } | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [angles, setAngles] = useState<{
    key: string;
    available: AngleInfo[];
    suggestions: AngleSuggestion[];
    winners: string[];
  } | null>(null);
  const [picks, setPicks] = useState<AnglePick[]>([]);
  const [ratios, setRatios] = useState<Ratio[]>(["4x5"]);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [templateId, setTemplateId] = useState<string | null>(null);

  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const product = products.find((p) => p.id === productId) ?? null;
  const body = useMemo<BriefSource>(() => {
    if (source === "product") {
      return { product_id: productId, price_text: price.trim(), real_urgency: urgency.trim() };
    }
    return { brief: { ...manual, price_text: price.trim(), real_urgency: urgency.trim(), bonuses: lines(bonusText) } };
  }, [source, productId, price, urgency, manual, bonusText]);
  const briefKey = JSON.stringify(body);

  useEffect(() => {
    void api.templates().then(setTemplates).catch(() => undefined);
  }, []);

  const manualOk =
    manual.niche.trim().length >= 2 &&
    [manual.product_name, manual.problem, manual.audience, manual.promise].every((v) => v.trim() !== "");
  const briefOk = source === "product" ? productId !== "" : manualOk;

  const go = (to: number) => {
    setError(null);
    setStep(to);
    window.scrollTo({ top: 0 });
  };

  const generateAvatars = async () => {
    setPending(true);
    setError(null);
    try {
      const result = await api.adsAvatars(body);
      setAvatars({ key: briefKey, list: result.avatars });
      setChosen(result.avatars.slice(0, 2).map((a) => a.name));
      setAngles(null);
      setPicks([]);
    } catch (e) {
      setError(message(e));
    } finally {
      setPending(false);
    }
  };

  const proposeAngles = async () => {
    const list = (avatars?.list ?? []).filter((a) => chosen.includes(a.name));
    setPending(true);
    setError(null);
    try {
      const result = await api.adsAngles({ ...body, avatars: list });
      const key = `${briefKey}|${chosen.join(",")}`;
      setAngles({ key, available: result.available, suggestions: result.suggestions, winners: result.winners ?? [] });
      setPicks(result.suggestions.slice(0, LIMITS.maxPicks).map((s) => ({ angle_id: s.angle_id, avatar: s.avatar, count: 2 })));
    } catch (e) {
      setError(message(e));
    } finally {
      setPending(false);
    }
  };

  const next = () => {
    if (step === 0) {
      go(1);
      if (avatars?.key !== briefKey) void generateAvatars();
    } else if (step === 1) {
      go(2);
      if (angles?.key !== `${briefKey}|${chosen.join(",")}`) void proposeAngles();
    }
  };

  const toggleRatio = (r: Ratio) =>
    setRatios((cur) => (cur.includes(r) ? cur.filter((x) => x !== r) : RATIOS.filter((x) => x === r || cur.includes(x))));

  const issue = validatePicks(picks);
  const canCreate = picks.length > 0 && ratios.length > 0 && issue === "none" && !pending;
  const effectiveTemplate = templateId ?? product?.template_id ?? DEFAULT_TEMPLATE;

  const create = async () => {
    setPending(true);
    setError(null);
    try {
      const list = (avatars?.list ?? []).filter((a) => chosen.includes(a.name));
      const result = await api.adsCreateBatch({
        ...body,
        avatars: list,
        picks,
        ratios,
        template_id: effectiveTemplate,
      });
      router.push(`/ads/${result.batch_id}`);
    } catch (e) {
      setError(message(e));
      setPending(false);
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
      <header className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="text-[26px] font-bold">{t("title")}</h1>
          <Link href="/ads" className="text-sm text-muted-foreground hover:underline">
            {t("back")}
          </Link>
        </div>
        <ol className="grid grid-cols-3 gap-2" aria-label={t("title")}>
          {STEPS.map((name, i) => (
            <li key={name}>
              <button
                type="button"
                onClick={() => i < step && go(i)}
                disabled={i > step}
                aria-current={i === step ? "step" : undefined}
                className={`w-full border-t-4 pt-2 text-left text-xs font-medium sm:text-sm ${
                  i <= step ? "border-primary text-foreground" : "border-muted text-muted-foreground"
                }`}
              >
                {i + 1}. {t(`steps.${name}`)}
              </button>
            </li>
          ))}
        </ol>
      </header>

      {error && <ErrorBox message={error} />}

      {step === 0 && (
        <section className="flex flex-col gap-5">
          <div className="flex gap-2" role="group" aria-label={t("brief.source")}>
            <Button
              variant={source === "product" ? "default" : "outline"}
              onClick={() => setSource("product")}
              disabled={products.length === 0}
            >
              {t("brief.fromProduct")}
            </Button>
            <Button variant={source === "manual" ? "default" : "outline"} onClick={() => setSource("manual")}>
              {t("brief.manual")}
            </Button>
          </div>

          {source === "product" ? (
            <div className="flex flex-col gap-2">
              <Label htmlFor="ad-product">{t("brief.product")}</Label>
              <select id="ad-product" value={productId} onChange={(e) => setProductId(e.target.value)} className={SELECT_CLASS}>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title ?? p.niche} · {p.market}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">{t("brief.productHint")}</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor="m-market">{t("brief.market")}</Label>
                <select
                  id="m-market"
                  value={manual.market}
                  onChange={(e) => setManual({ ...manual, market: e.target.value as Market })}
                  className={SELECT_CLASS}
                >
                  <option value="es-LATAM">es-LATAM</option>
                  <option value="pt-BR">pt-BR</option>
                </select>
              </div>
              {(["niche", "product_name"] as const).map((f) => (
                <div key={f} className="flex flex-col gap-2">
                  <Label htmlFor={`m-${f}`}>{t(`brief.${f}`)}</Label>
                  <Input id={`m-${f}`} value={manual[f]} onChange={(e) => setManual({ ...manual, [f]: e.target.value })} maxLength={f === "niche" ? 120 : 300} />
                </div>
              ))}
              {(["problem", "audience", "promise"] as const).map((f) => (
                <div key={f} className="flex flex-col gap-2 sm:col-span-2">
                  <Label htmlFor={`m-${f}`}>{t(`brief.${f}`)}</Label>
                  <Textarea id={`m-${f}`} value={manual[f]} onChange={(e) => setManual({ ...manual, [f]: e.target.value })} maxLength={500} />
                </div>
              ))}
              <div className="flex flex-col gap-2 sm:col-span-2">
                <Label htmlFor="m-bonuses">{t("brief.bonuses")}</Label>
                <Textarea id="m-bonuses" value={bonusText} onChange={(e) => setBonusText(e.target.value)} placeholder={t("brief.bonusesHint")} />
              </div>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="ad-price">{t("brief.price")}</Label>
              <Input id="ad-price" value={price} onChange={(e) => setPrice(e.target.value)} maxLength={60} placeholder="USD 12" />
              <p className="text-xs text-muted-foreground">{t("brief.priceHint")}</p>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="ad-urgency">{t("brief.urgency")}</Label>
              <Input id="ad-urgency" value={urgency} onChange={(e) => setUrgency(e.target.value)} maxLength={200} />
              <p className="text-xs text-muted-foreground">{t("brief.urgencyHint")}</p>
            </div>
          </div>

          <ProofsPanel productId={source === "product" ? productId : undefined} />
          <StepNav onNext={next} nextDisabled={!briefOk} />
        </section>
      )}

      {step === 1 && (
        <section className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">{t("avatars.hint")}</p>
          {pending && !avatars && <Loading text={t("avatars.loading")} />}
          <div className="grid gap-3 sm:grid-cols-2">
            {avatars?.list.map((a) => {
              const on = chosen.includes(a.name);
              return (
                <label
                  key={a.name}
                  className={`flex cursor-pointer flex-col gap-2 rounded-xl border p-4 text-sm transition-colors ${
                    on ? "border-primary bg-primary/5" : "hover:bg-muted/40"
                  }`}
                >
                  <span className="flex items-center gap-2 font-medium">
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => setChosen((cur) => (on ? cur.filter((n) => n !== a.name) : [...cur, a.name]))}
                    />
                    {a.name}
                  </span>
                  <span className="text-muted-foreground">{a.situation}</span>
                  <span>
                    <strong>{t("avatars.pain")}:</strong> {a.pain}
                  </span>
                  <span>
                    <strong>{t("avatars.desire")}:</strong> {a.desire}
                  </span>
                </label>
              );
            })}
          </div>
          <div className="flex justify-end">
            <ConfirmButton
              size="default"
              label={t("avatars.regenerate")}
              confirmLabel={t("confirmAi")}
              onConfirm={() => void generateAvatars()}
              disabled={pending}
              icon={<Sparkles aria-hidden />}
            />
          </div>
          <StepNav onBack={() => go(0)} onNext={next} nextDisabled={chosen.length === 0 || !avatars} pending={pending} />
        </section>
      )}

      {step === 2 && (
        <section className="flex flex-col gap-5">
          <p className="text-sm text-muted-foreground">{t("angles.hint")}</p>
          {angles && angles.winners.length > 0 && (
            <p className="rounded-lg bg-emerald-500/10 p-3 text-sm">{t("angles.winnersHint")}</p>
          )}
          {pending && !angles && <Loading text={t("angles.loading")} />}
          {angles && (
            <>
              <ul className="flex flex-col gap-3">
                {picks.map((p, i) => {
                  const info = angles.available.find((a) => a.id === p.angle_id);
                  const why = angles.suggestions.find((s) => s.angle_id === p.angle_id && s.avatar === p.avatar)?.why;
                  return (
                    <li key={`${p.angle_id}|${p.avatar}|${i}`} className="flex flex-col gap-2 rounded-xl border p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="flex flex-wrap items-center gap-2 font-medium">
                            {info?.name ?? p.angle_id}
                            {angles.winners.includes(p.angle_id) && (
                              <Badge variant="secondary" className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                                <Trophy aria-hidden />
                                {t("angles.winner")}
                              </Badge>
                            )}
                          </p>
                          <p className="text-xs text-muted-foreground">{why ?? info?.description}</p>
                        </div>
                        <Button variant="ghost" size="icon-sm" onClick={() => setPicks(picks.filter((_, j) => j !== i))} aria-label={t("angles.remove")}>
                          <X aria-hidden />
                        </Button>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-[1fr_8rem]">
                        <select
                          value={p.avatar}
                          onChange={(e) => setPicks(picks.map((x, j) => (j === i ? { ...x, avatar: e.target.value } : x)))}
                          className={SELECT_CLASS}
                          aria-label={t("angles.avatar")}
                        >
                          {chosen.map((n) => (
                            <option key={n} value={n}>
                              {n}
                            </option>
                          ))}
                        </select>
                        <select
                          value={p.count}
                          onChange={(e) => setPicks(picks.map((x, j) => (j === i ? { ...x, count: Number(e.target.value) } : x)))}
                          className={SELECT_CLASS}
                          aria-label={t("angles.count")}
                        >
                          {Array.from({ length: LIMITS.maxCount }, (_, k) => k + 1).map((n) => (
                            <option key={n} value={n}>
                              {t("angles.variations", { count: n })}
                            </option>
                          ))}
                        </select>
                      </div>
                    </li>
                  );
                })}
              </ul>
              <div className="flex flex-col gap-2">
                <Label htmlFor="add-angle">{t("angles.add")}</Label>
                <select
                  id="add-angle"
                  value=""
                  onChange={(e) => e.target.value && setPicks([...picks, { angle_id: e.target.value, avatar: chosen[0], count: 2 }])}
                  className={SELECT_CLASS}
                  disabled={picks.length >= LIMITS.maxPicks}
                >
                  <option value="">{t("angles.choose")}</option>
                  {angles.available.map((a) => (
                    <option key={a.id} value={a.id}>
                      {angles.winners.includes(a.id) ? `★ ${a.name}` : a.name}
                    </option>
                  ))}
                </select>
              </div>

              <fieldset className="flex flex-col gap-2">
                <legend className="mb-1 text-sm font-medium">{t("formats.title")}</legend>
                <div className="flex flex-wrap gap-3">
                  {RATIOS.map((r) => (
                    <label key={r} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                      <input type="checkbox" checked={ratios.includes(r)} onChange={() => toggleRatio(r)} />
                      {t(`formats.${r}`)}
                    </label>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">{t("formats.hint")}</p>
              </fieldset>

              <div className="flex flex-col gap-2">
                <Label htmlFor="ad-template">{t("template.label")}</Label>
                <select id="ad-template" value={effectiveTemplate} onChange={(e) => setTemplateId(e.target.value)} className={SELECT_CLASS}>
                  {(templates.length ? templates : [{ id: effectiveTemplate, name: effectiveTemplate }]).map((tpl) => (
                    <option key={tpl.id} value={tpl.id}>
                      {tpl.name}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground">{t("template.hint")}</p>
              </div>

              <p className="rounded-lg bg-muted/40 p-3 text-sm" aria-live="polite">
                {t("angles.summary", { drafts: draftCount(picks), images: creativeCount(picks, ratios) })}
              </p>
              {issue !== "none" && <p className="text-sm text-destructive">{t(`issues.${issue}`, { max: LIMITS.maxCreativesPerBatch })}</p>}
            </>
          )}
          <div className="sticky bottom-0 flex justify-between gap-3 border-t bg-background/95 py-4 backdrop-blur">
            <Button variant="outline" onClick={() => go(1)} disabled={pending}>
              {tc("back")}
            </Button>
            <ConfirmButton
              size="lg"
              label={t("create")}
              confirmLabel={t("confirmAi")}
              onConfirm={() => void create()}
              disabled={!canCreate}
              icon={<Sparkles aria-hidden />}
            />
          </div>
        </section>
      )}
    </main>
  );
}
