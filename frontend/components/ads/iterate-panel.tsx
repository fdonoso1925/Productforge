"use client";

import { Copy, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { ConfirmButton } from "@/components/product/confirm-button";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ErrorBox } from "@/components/wizard/step-nav";
import { type CreativeGroup, RATIOS, type Ratio } from "@/lib/ads";
import { ApiError, api } from "@/lib/api";

const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";

function message(e: unknown): string {
  if (e instanceof ApiError) return e.errors.length ? e.errors.join(" · ") : e.message;
  return e instanceof Error ? e.message : String(e);
}

/**
 * Iterar un borrador: hooks nuevos con IA (mismo ángulo y avatar) o una variante con el mismo
 * texto en otra plantilla o formato (sin IA). El original no se toca.
 */
export function IteratePanel({
  group,
  onDone,
  disabled,
}: {
  group: CreativeGroup;
  onDone: () => void;
  disabled: boolean;
}) {
  const t = useTranslations("ads.iterate");
  const tt = useTranslations("ads.templates");
  const tf = useTranslations("ads.wizard.formats");
  const [templates, setTemplates] = useState<string[]>([]);
  const [template, setTemplate] = useState(group.lead.template_id);
  const [ratio, setRatio] = useState<Ratio>(group.lead.ratio);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void api
      .adsTemplates()
      .then((r) => alive && setTemplates(r.templates.map((x) => x.id)))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const run = async (action: () => Promise<unknown>) => {
    setPending(true);
    setError(null);
    try {
      await action();
      onDone();
    } catch (e) {
      setError(message(e));
    } finally {
      setPending(false);
    }
  };

  const unchanged = template === group.lead.template_id && ratio === group.lead.ratio;

  return (
    <section className="flex flex-col gap-4 rounded-xl border bg-muted/30 p-4" aria-label={t("title")}>
      <div>
        <h3 className="font-semibold">{t("title")}</h3>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">{t("hooksTitle")}</p>
        <p className="text-xs text-muted-foreground">{t("hooksHint")}</p>
        <div>
          <ConfirmButton
            label={t("hooks")}
            confirmLabel={t("confirmAi")}
            onConfirm={() => void run(() => api.adsIterate(group.lead.id, 2))}
            disabled={disabled || pending}
            icon={<RefreshCw aria-hidden />}
          />
        </div>
      </div>
      <div className="flex flex-col gap-2 border-t pt-4">
        <p className="text-sm font-medium">{t("variantTitle")}</p>
        <p className="text-xs text-muted-foreground">{t("variantHint")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor={`v-t-${group.id}`}>{t("template")}</Label>
            <select id={`v-t-${group.id}`} value={template} onChange={(e) => setTemplate(e.target.value)} className={SELECT_CLASS}>
              {(templates.length ? templates : [group.lead.template_id]).map((id) => (
                <option key={id} value={id}>
                  {tt(id)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor={`v-r-${group.id}`}>{t("format")}</Label>
            <select id={`v-r-${group.id}`} value={ratio} onChange={(e) => setRatio(e.target.value as Ratio)} className={SELECT_CLASS}>
              {RATIOS.map((r) => (
                <option key={r} value={r}>
                  {tf(r)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <Button
            variant="outline"
            size="sm"
            disabled={disabled || pending || unchanged}
            onClick={() =>
              void run(() =>
                api.adsVariant(group.lead.id, {
                  ...(template !== group.lead.template_id ? { template_id: template } : {}),
                  ...(ratio !== group.lead.ratio ? { ratio } : {}),
                }),
              )
            }
          >
            <Copy aria-hidden />
            {t("createVariant")}
          </Button>
        </div>
      </div>
    </section>
  );
}
