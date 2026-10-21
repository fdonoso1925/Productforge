"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorBox } from "@/components/wizard/step-nav";
import { useRouter } from "@/i18n/navigation";
import { ApiError, api, type RemodelBody } from "@/lib/api";
import { BONUS_FORMATS, planRemodel } from "@/lib/remodel";
import { FORMATS, type Format, type ItemRow, type ProductRow, type TemplateInfo } from "@/lib/types";

/** Formulario para crear una versión nueva con otra plantilla, formato, tono o público. */
export function RemodelPanel({
  product,
  items,
  onClose,
}: {
  product: ProductRow;
  items: ItemRow[];
  onClose: () => void;
}) {
  const t = useTranslations("product.actions");
  const tf = useTranslations("formats");
  const tr = useTranslations("roles");
  const router = useRouter();
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [templateId, setTemplateId] = useState(product.template_id);
  const [tone, setTone] = useState(product.tone ?? "");
  const [audience, setAudience] = useState(product.audience_override ?? "");
  const [formats, setFormats] = useState<Record<string, Format>>({});
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<{ message: string; errors: string[] } | null>(null);

  useEffect(() => {
    api.templates().then(setTemplates, () => setTemplates([]));
  }, []);

  const changedFormats = useMemo(
    () => Object.fromEntries(items.filter((i) => formats[i.id] && formats[i.id] !== i.format).map((i) => [i.id, formats[i.id]])),
    [items, formats],
  );
  const toneChanged = tone.trim() !== (product.tone ?? "");
  const audienceChanged = audience.trim() !== (product.audience_override ?? "");
  const templateChanged = templateId !== product.template_id;
  const hasChanges = templateChanged || toneChanged || audienceChanged || Object.keys(changedFormats).length > 0;
  const plan = planRemodel(items, changedFormats, toneChanged || audienceChanged);

  const submit = async () => {
    const body: RemodelBody = {};
    if (templateChanged) body.template_id = templateId;
    if (toneChanged) body.tone = tone.trim() || null;
    if (audienceChanged) body.audience_override = audience.trim() || null;
    if (Object.keys(changedFormats).length > 0) body.formats = changedFormats;
    setPending(true);
    setError(null);
    try {
      const { product_id } = await api.remodel(product.id, body);
      router.push(`/products/${product_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? { message: e.message, errors: e.errors } : { message: String(e), errors: [] });
      setPending(false);
    }
  };

  return (
    <section className="flex min-w-0 flex-col gap-5 rounded-xl border bg-muted/30 p-4" aria-label={t("remodelTitle")}>
      <div>
        <h2 className="font-semibold">{t("remodelTitle")}</h2>
        <p className="text-sm text-muted-foreground">{t("remodelHint")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-[1fr_9rem]">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="remodel-template">{t("template")}</Label>
          <select
            id="remodel-template"
            className="h-8 rounded-lg border border-input bg-background px-2 text-sm"
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
          >
            {(templates.length ? templates : [{ id: product.template_id, name: product.template_id }]).map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.name}
              </option>
            ))}
          </select>
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element -- miniatura servida por el backend */}
        <img src={api.previewUrl(templateId)} alt="" className="hidden w-36 rounded border sm:block" />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="remodel-tone">{t("tone")}</Label>
          <Input id="remodel-tone" maxLength={200} placeholder={t("tonePlaceholder")} value={tone} onChange={(e) => setTone(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="remodel-audience">{t("audience")}</Label>
          <Input
            id="remodel-audience"
            maxLength={300}
            placeholder={t("audiencePlaceholder")}
            value={audience}
            onChange={(e) => setAudience(e.target.value)}
          />
        </div>
      </div>

      <fieldset className="flex min-w-0 flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">{t("formats")}</legend>
        {items.map((item) => {
          const options = item.role === "bonus" ? BONUS_FORMATS : FORMATS;
          return (
            <div key={item.id} className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
              <span className="min-w-0 truncate text-sm">
                {item.title} <span className="text-xs text-muted-foreground">· {tr(item.role)}</span>
              </span>
              <select
                aria-label={item.title}
                className="h-8 shrink-0 rounded-lg border border-input bg-background px-2 text-sm"
                value={formats[item.id] ?? item.format}
                onChange={(e) => setFormats((f) => ({ ...f, [item.id]: e.target.value as Format }))}
              >
                {options.map((f) => (
                  <option key={f} value={f}>
                    {tf(`${f}.name`)}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </fieldset>

      <div className="flex flex-col gap-1 text-sm" aria-live="polite">
        {hasChanges ? (
          <>
            {plan.generate > 0 && <span className="font-medium text-amber-700 dark:text-amber-400">{t("planAi", { count: plan.generate })}</span>}
            {plan.rerender > 0 && <span className="text-muted-foreground">{t("planFree", { count: plan.rerender })}</span>}
          </>
        ) : (
          <span className="text-muted-foreground">{t("planNone")}</span>
        )}
      </div>

      {error && (
        <div className="flex flex-col gap-2">
          <ErrorBox message={error.message} />
          {error.errors.length > 0 && (
            <ul className="list-disc pl-6 text-sm text-destructive">
              {error.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={onClose} disabled={pending}>
          {t("cancel")}
        </Button>
        <Button onClick={submit} disabled={!hasChanges || pending}>
          {pending ? t("working") : t("apply")}
        </Button>
      </div>
    </section>
  );
}
