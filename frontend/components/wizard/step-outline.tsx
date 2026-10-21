"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useRouter } from "@/i18n/navigation";
import { ApiError, api } from "@/lib/api";
import { FORMAT_ICONS } from "@/lib/formats";
import { outlineSchema } from "@/lib/schemas";
import { FORMATS, type Format, type ItemOutline, type PackageOutline } from "@/lib/types";
import { ErrorBox, Loading, StepNav } from "./step-nav";
import { inputsKey, type StepProps } from "./wizard";

type Slot = { group: "main" | "order_bumps" | "bonuses"; index: number };

export function StepOutline({ state, update, nav }: StepProps) {
  const t = useTranslations("wizard.outline");
  const router = useRouter();
  const [error, setError] = useState<{ message: string; errors: string[] } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const requested = useRef<string | null>(null);
  const key = inputsKey(state);
  const current = state.built?.key === key ? state.built : null;
  const draft = current?.outline ?? null;
  const loading = !current && !error;

  // Arma el outline (y crea el producto) cuando cambian las elecciones del wizard.
  // El ref evita crear dos productos si React monta el efecto dos veces.
  useEffect(() => {
    const request = `${key}|${attempt}`;
    if (current || !state.problem || requested.current === request) return;
    requested.current = request;
    api
      .buildOutline({
        niche: state.niche,
        problem: state.problem,
        market: state.market,
        main_format: state.format,
        template_id: state.templateId,
      })
      .then(
        ({ product_id, outline }) => {
          update({ built: { key, productId: product_id, outline, dirty: false } });
        },
        (e) => setError(toError(e)),
      );
  }, [current, key, attempt, state.niche, state.problem, state.market, state.format, state.templateId, update]);

  const build = () => {
    setError(null);
    setAttempt((n) => n + 1);
  };
  // Las ediciones viven en el estado del wizard: sobreviven si el usuario vuelve atrás.
  const setDraft = (outline: PackageOutline) =>
    current && update({ built: { ...current, outline, dirty: true } });

  const edit = (slot: Slot, patch: Partial<ItemOutline>) => {
    if (!draft) return;
    const next = structuredClone(draft);
    if (slot.group === "main") next.main = { ...next.main, ...patch };
    else next[slot.group][slot.index] = { ...next[slot.group][slot.index], ...patch };
    setDraft(next);
  };

  const parsed = draft ? outlineSchema.safeParse(draft) : null;

  const submit = async () => {
    if (!draft || !current || !parsed?.success) return;
    setSubmitting(true);
    setError(null);
    try {
      if (current.dirty) {
        await api.saveOutline(current.productId, parsed.data as PackageOutline);
        update({ built: { ...current, dirty: false } });
      }
      await api.generate(current.productId);
      router.push(`/products/${current.productId}`);
    } catch (e) {
      setError(toError(e));
      setSubmitting(false);
    }
  };

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">{t("heading")}</h2>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>

      {loading && <Loading text={t("loading")} />}
      {error && (
        <div className="flex flex-col gap-2">
          <ErrorBox message={error.message} onRetry={draft ? undefined : build} />
          {error.errors.length > 0 && (
            <ul className="list-disc pl-6 text-sm text-destructive">
              {error.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {draft && !loading && (
        <>
          <div className="flex max-w-xl flex-col gap-1.5">
            <Label htmlFor="product-name">{t("productName")}</Label>
            <Input
              id="product-name"
              maxLength={300}
              value={draft.product_name}
              onChange={(e) => {
                setDraft({ ...draft, product_name: e.target.value });
              }}
            />
          </div>
          <ItemCard item={draft.main} onChange={(p) => edit({ group: "main", index: 0 }, p)} lockFormat />
          {draft.order_bumps.map((item, index) => (
            <ItemCard key={`b${index}`} item={item} onChange={(p) => edit({ group: "order_bumps", index }, p)} />
          ))}
          {draft.bonuses.map((item, index) => (
            <ItemCard key={`n${index}`} item={item} onChange={(p) => edit({ group: "bonuses", index }, p)} />
          ))}
          {parsed && !parsed.success && (
            <p className="text-sm text-destructive">
              {t("invalid")} ({parsed.error.issues[0]?.path.join(" › ")})
            </p>
          )}
        </>
      )}

      <StepNav
        onBack={nav.back}
        onNext={submit}
        nextLabel={t("generate")}
        nextDisabled={!draft || loading || !parsed?.success}
        pending={submitting}
      />
    </section>
  );
}

function toError(e: unknown) {
  if (e instanceof ApiError) return { message: e.message, errors: e.errors };
  return { message: e instanceof Error ? e.message : String(e), errors: [] };
}

function ItemCard({
  item,
  onChange,
  lockFormat,
}: {
  item: ItemOutline;
  onChange: (patch: Partial<ItemOutline>) => void;
  lockFormat?: boolean;
}) {
  const t = useTranslations("wizard.outline");
  const tr = useTranslations("roles");
  const tf = useTranslations("formats");
  const Icon = FORMAT_ICONS[item.format];

  return (
    <article className="grid gap-3 rounded-xl border p-4 md:grid-cols-[1fr_12rem]">
      <div className="flex flex-wrap items-center gap-2 md:col-span-2">
        <Badge variant={item.role === "main" ? "default" : "secondary"}>{tr(item.role)}</Badge>
        <Icon className="size-4 text-muted-foreground" aria-hidden />
        {lockFormat ? (
          <span className="text-sm text-muted-foreground">{tf(`${item.format}.name`)}</span>
        ) : (
          <select
            aria-label="format"
            className="rounded-md border bg-background px-2 py-1 text-sm"
            value={item.format}
            onChange={(e) => onChange({ format: e.target.value as Format })}
          >
            {FORMATS.map((f) => (
              <option key={f} value={f}>
                {tf(`${f}.name`)}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="flex flex-col gap-3">
        <Labeled label={t("itemTitle")}>
          <Input maxLength={300} value={item.title} onChange={(e) => onChange({ title: e.target.value })} />
        </Labeled>
        <Labeled label={t("promise")}>
          <Textarea maxLength={800} rows={2} value={item.promise} onChange={(e) => onChange({ promise: e.target.value })} />
        </Labeled>
        {item.role === "bonus" && (
          <Labeled label={t("objection")}>
            <Input
              maxLength={500}
              value={item.objection_addressed ?? ""}
              onChange={(e) => onChange({ objection_addressed: e.target.value })}
            />
          </Labeled>
        )}
      </div>
      <div className="flex flex-col gap-3">
        <Labeled label={t("toc")}>
          <Textarea
            rows={6}
            value={item.table_of_contents.join("\n")}
            onChange={(e) =>
              onChange({ table_of_contents: e.target.value.split("\n").map((l) => l.trimStart()).filter(Boolean) })
            }
          />
        </Labeled>
        <Labeled label={t("pages")}>
          <Input
            type="number"
            min={1}
            max={60}
            value={item.estimated_pages}
            onChange={(e) => onChange({ estimated_pages: Number(e.target.value) || 1 })}
          />
        </Labeled>
      </div>
    </article>
  );
}

function Labeled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
