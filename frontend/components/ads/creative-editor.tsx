"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorBox } from "@/components/wizard/step-nav";
import {
  type AdCopy,
  copyIssues,
  type CreativeRow,
  type ImageCopy,
  LIMITS,
  lines,
  META_CTAS,
  wordCount,
} from "@/lib/ads";
import { ApiError, api } from "@/lib/api";

/** «a, b ,c» → ["a", "b", "c"] (sin vacíos ni palabras larguísimas). */
function keywords(text: string): string[] {
  return text
    .split(",")
    .map((k) => k.trim().slice(0, LIMITS.keywordMax))
    .filter(Boolean);
}

const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";

function Counter({ value, max, unit }: { value: number; max: number; unit: "words" | "chars" }) {
  const t = useTranslations("ads.editor");
  return (
    <span className={`text-xs ${value > max ? "text-destructive" : "text-muted-foreground"}`}>
      {t(unit, { n: value, max })}
    </span>
  );
}

/**
 * Editor rápido del texto de un creativo. Editar y volver a componer NO usa IA. El backend valida
 * con las mismas reglas y recalcula el semáforo de políticas; aquí solo se avisa antes de enviar.
 */
export function CreativeEditor({
  creative,
  onSaved,
  onClose,
}: {
  creative: CreativeRow;
  onSaved: () => void;
  onClose: () => void;
}) {
  const t = useTranslations("ads.editor");
  const [image, setImage] = useState<ImageCopy>(creative.copy.image);
  const [ad, setAd] = useState<AdCopy>(creative.copy.ad);
  const [bulletText, setBulletText] = useState(creative.copy.image.bullets.join("\n"));
  // La foto de fondo: lo que se busca en el banco de imágenes (inglés, separado por comas).
  const [keywordText, setKeywordText] = useState(creative.copy.stock_keywords.join(", "));
  const [scene, setScene] = useState(creative.copy.scene);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const draft = useMemo(
    () => ({
      ...creative.copy,
      image: { ...image, bullets: lines(bulletText) },
      ad,
      scene,
      stock_keywords: keywords(keywordText),
    }),
    [creative.copy, image, ad, bulletText, scene, keywordText],
  );
  const issues = useMemo(() => copyIssues(draft), [draft]);
  const templateId = creative.template_id;
  const usesBullets = ["checklist", "product_mockup", "before_after", "comparison", "offer_stack"].includes(templateId);
  const usesNote = ["note", "testimonial"].includes(templateId);

  const setImg = <K extends keyof ImageCopy>(key: K, value: ImageCopy[K]) => setImage((cur) => ({ ...cur, [key]: value }));
  const setAdField = <K extends keyof AdCopy>(key: K, value: AdCopy[K]) => setAd((cur) => ({ ...cur, [key]: value }));

  const save = async () => {
    setPending(true);
    setError(null);
    try {
      // La foto solo viaja si cambió: así un creativo anterior (sin escena guardada) se edita igual.
      const photoChanged = scene !== creative.copy.scene || keywordText !== creative.copy.stock_keywords.join(", ");
      await api.adsEdit(creative.id, {
        image: draft.image,
        ad,
        ...(photoChanged ? { stock_keywords: draft.stock_keywords, scene: scene.trim() } : {}),
      });
      onSaved();
    } catch (e) {
      setError(
        e instanceof ApiError ? (e.errors.length ? e.errors.join(" · ") : e.message) : e instanceof Error ? e.message : String(e),
      );
      setPending(false);
    }
  };

  return (
    <section className="flex flex-col gap-4 rounded-xl border bg-muted/30 p-4" aria-label={t("title")}>
      <div>
        <h3 className="font-semibold">{t("title")}</h3>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1 sm:col-span-2">
          <Label htmlFor={`h-${creative.id}`}>{t("imageHeadline")}</Label>
          <Input id={`h-${creative.id}`} value={image.headline} onChange={(e) => setImg("headline", e.target.value)} />
          <Counter value={wordCount(image.headline)} max={LIMITS.imageHeadlineWords} unit="words" />
        </div>
        <div className="flex flex-col gap-1 sm:col-span-2">
          <Label htmlFor={`s-${creative.id}`}>{t("imageSub")}</Label>
          <Input id={`s-${creative.id}`} value={image.subheadline} onChange={(e) => setImg("subheadline", e.target.value)} />
          <Counter value={wordCount(image.subheadline)} max={LIMITS.imageSubWords} unit="words" />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`k-${creative.id}`}>{t("kicker")}</Label>
          <Input id={`k-${creative.id}`} value={image.kicker} onChange={(e) => setImg("kicker", e.target.value)} />
          <Counter value={wordCount(image.kicker)} max={LIMITS.kickerWords} unit="words" />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`c-${creative.id}`}>{t("imageCta")}</Label>
          <Input id={`c-${creative.id}`} value={image.cta_text} onChange={(e) => setImg("cta_text", e.target.value)} />
          <Counter value={wordCount(image.cta_text)} max={LIMITS.ctaWords} unit="words" />
        </div>
        {usesBullets && (
          <div className="flex flex-col gap-1 sm:col-span-2">
            <Label htmlFor={`b-${creative.id}`}>{t("bullets")}</Label>
            <Textarea id={`b-${creative.id}`} value={bulletText} onChange={(e) => setBulletText(e.target.value)} />
            <span className="text-xs text-muted-foreground">{t("bulletsHint")}</span>
          </div>
        )}
        {usesNote && (
          <div className="flex flex-col gap-1 sm:col-span-2">
            <Label htmlFor={`n-${creative.id}`}>{t(templateId === "testimonial" ? "quote" : "note")}</Label>
            <Textarea id={`n-${creative.id}`} value={image.note} onChange={(e) => setImg("note", e.target.value)} />
            <Counter value={image.note.length} max={LIMITS.noteMax} unit="chars" />
            {templateId === "testimonial" && <span className="text-xs text-muted-foreground">{t("quoteHint")}</span>}
          </div>
        )}
        {templateId === "checklist" && (
          <div className="flex flex-col gap-1">
            <Label htmlFor={`m-${creative.id}`}>{t("mark")}</Label>
            <select
              id={`m-${creative.id}`}
              value={image.mark}
              onChange={(e) => setImg("mark", e.target.value as ImageCopy["mark"])}
              className={SELECT_CLASS}
            >
              <option value="check">{t("markCheck")}</option>
              <option value="cross">{t("markCross")}</option>
            </select>
          </div>
        )}
      </div>

      <div className="grid gap-4 border-t pt-4 sm:grid-cols-2">
        <p className="text-sm font-medium sm:col-span-2">{t("photo")}</p>
        <p className="-mt-2 text-xs text-muted-foreground sm:col-span-2">{t("photoHint")}</p>
        <div className="flex flex-col gap-1 sm:col-span-2">
          <Label htmlFor={`kw-${creative.id}`}>{t("photoKeywords")}</Label>
          <Input
            id={`kw-${creative.id}`}
            value={keywordText}
            onChange={(e) => setKeywordText(e.target.value)}
            placeholder="home office, sunrise"
          />
          <span className="text-xs text-muted-foreground">{t("photoKeywordsHint")}</span>
        </div>
        <div className="flex flex-col gap-1 sm:col-span-2">
          <Label htmlFor={`sc-${creative.id}`}>{t("photoScene")}</Label>
          <Input id={`sc-${creative.id}`} value={scene} onChange={(e) => setScene(e.target.value)} maxLength={LIMITS.sceneMax} />
        </div>
      </div>

      <div className="grid gap-4 border-t pt-4 sm:grid-cols-2">
        <p className="text-sm font-medium sm:col-span-2">{t("adsManager")}</p>
        <div className="flex flex-col gap-1 sm:col-span-2">
          <Label htmlFor={`ps-${creative.id}`}>{t("primaryShort")}</Label>
          <Textarea id={`ps-${creative.id}`} value={ad.primary_short} onChange={(e) => setAdField("primary_short", e.target.value)} />
          <Counter value={ad.primary_short.length} max={LIMITS.primaryShortMax} unit="chars" />
        </div>
        <div className="flex flex-col gap-1 sm:col-span-2">
          <Label htmlFor={`pl-${creative.id}`}>{t("primaryLong")}</Label>
          <Textarea id={`pl-${creative.id}`} value={ad.primary_long} onChange={(e) => setAdField("primary_long", e.target.value)} className="min-h-32" />
          <Counter value={ad.primary_long.length} max={LIMITS.primaryLong[1]} unit="chars" />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`ah-${creative.id}`}>{t("adHeadline")}</Label>
          <Input id={`ah-${creative.id}`} value={ad.headline} onChange={(e) => setAdField("headline", e.target.value)} />
          <Counter value={ad.headline.length} max={LIMITS.headlineMax} unit="chars" />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`ad-${creative.id}`}>{t("description")}</Label>
          <Input id={`ad-${creative.id}`} value={ad.description} onChange={(e) => setAdField("description", e.target.value)} />
          <Counter value={ad.description.length} max={LIMITS.descriptionMax} unit="chars" />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`cta-${creative.id}`}>{t("cta")}</Label>
          <select
            id={`cta-${creative.id}`}
            value={ad.cta}
            onChange={(e) => setAdField("cta", e.target.value as AdCopy["cta"])}
            className={SELECT_CLASS}
          >
            {META_CTAS.map((c) => (
              <option key={c} value={c}>
                {t(`ctas.${c}`)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {issues.length > 0 && (
        <ul className="list-disc rounded-lg bg-amber-500/10 p-3 pl-7 text-sm" aria-live="polite">
          {issues.map((issue) => (
            <li key={issue.key + JSON.stringify(issue.values)}>{t(`issues.${issue.key}`, issue.values ?? {})}</li>
          ))}
        </ul>
      )}
      {error && <ErrorBox message={error} />}
      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={onClose} disabled={pending}>
          {t("cancel")}
        </Button>
        <Button onClick={save} disabled={pending}>
          {pending ? t("saving") : t("save")}
        </Button>
      </div>
    </section>
  );
}
