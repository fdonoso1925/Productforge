"use client";

import { Ban, ImagePlus, Sparkles, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { ART_CHOICES, checkCoverFile, COVER_IMAGE_TYPES } from "@/lib/cover";
import type { ArtChoice, CoverSpec } from "@/lib/types";

/**
 * Elige la portada: un estilo de arte generativo (único por pieza, de la misma familia en todo el
 * paquete) o una imagen propia opcional que lo reemplaza. La plantilla sigue aplicándose a todo el PDF.
 */
export function CoverPicker({
  templateId,
  value,
  onChange,
  disabled,
}: {
  templateId: string;
  value: CoverSpec;
  onChange: (next: CoverSpec) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("cover");
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const hasImage = value.image_id !== null;

  // Si ya hay una imagen elegida (p. ej. al remodelar o volver al paso), trae su miniatura.
  useEffect(() => {
    if (!value.image_id || imageUrl) return;
    let alive = true;
    api.coverImageUrl(value.image_id).then(
      ({ url }) => alive && setImageUrl(url),
      () => alive && setImageUrl(null),
    );
    return () => {
      alive = false;
    };
  }, [value.image_id, imageUrl]);

  const upload = async (file: File) => {
    setError(null);
    const problem = checkCoverFile(file);
    if (problem) return setError(t(problem === "type" ? "errorType" : "errorSize"));
    setUploading(true);
    try {
      const result = await api.uploadCoverImage(file);
      setImageUrl(result.url);
      onChange({ ...value, image_id: result.image_id });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errorUpload"));
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  };

  const remove = () => {
    setImageUrl(null);
    setError(null);
    onChange({ ...value, image_id: null });
  };

  const hintKey = value.art === "auto" ? "auto" : value.art === "none" ? "none" : "style";

  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("title")}>
      <div>
        <h3 className="font-semibold">{t("title")}</h3>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>

      <div
        role="radiogroup"
        aria-label={t("styleLabel")}
        className={`grid grid-cols-2 gap-3 sm:grid-cols-4 ${hasImage ? "opacity-50" : ""}`}
      >
        {ART_CHOICES.map((choice: ArtChoice) => {
          const selected = value.art === choice;
          return (
            <button
              key={choice}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled || hasImage}
              onClick={() => onChange({ ...value, art: choice })}
              className={`flex min-w-0 flex-col gap-1.5 rounded-lg border p-2 text-left text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed ${
                selected ? "border-primary ring-2 ring-primary" : "hover:border-foreground/40"
              }`}
            >
              <span className="relative flex aspect-[210/297] w-full items-center justify-center overflow-hidden rounded border bg-muted">
                {choice === "auto" && <Sparkles className="size-6 text-muted-foreground" aria-hidden />}
                {choice === "none" && <Ban className="size-6 text-muted-foreground" aria-hidden />}
                {choice !== "auto" && choice !== "none" && (
                  // eslint-disable-next-line @next/next/no-img-element -- SVG servido por el backend
                  <img src={api.artPreviewUrl(choice, templateId)} alt="" className="size-full object-cover" loading="lazy" />
                )}
              </span>
              <span className="truncate font-medium">{t(`styles.${choice}`)}</span>
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">{hasImage ? t("imageReplaces") : t(`styleHint.${hintKey}`)}</p>

      <div className="flex flex-col gap-2 rounded-lg border border-dashed p-3">
        <div className="flex flex-wrap items-center gap-3">
          {imageUrl && (
            // eslint-disable-next-line @next/next/no-img-element -- miniatura firmada de Supabase Storage
            <img src={imageUrl} alt={t("imageAlt")} className="h-20 w-14 rounded border object-cover" />
          )}
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="text-sm font-medium">{t("imageTitle")}</span>
            <span className="text-xs text-muted-foreground">{t("imageHint")}</span>
          </div>
          <input
            ref={input}
            type="file"
            accept={COVER_IMAGE_TYPES.join(",")}
            className="sr-only"
            aria-label={t("imageTitle")}
            disabled={disabled || uploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          <Button type="button" variant="outline" size="sm" disabled={disabled || uploading} onClick={() => input.current?.click()}>
            <ImagePlus className="size-4" aria-hidden />
            {uploading ? t("uploading") : hasImage ? t("replace") : t("upload")}
          </Button>
          {hasImage && (
            <Button type="button" variant="ghost" size="sm" disabled={disabled || uploading} onClick={remove}>
              <Trash2 className="size-4" aria-hidden />
              {t("remove")}
            </Button>
          )}
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}
