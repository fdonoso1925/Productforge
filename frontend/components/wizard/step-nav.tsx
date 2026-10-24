"use client";

import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

export function StepNav({
  onBack,
  onNext,
  nextDisabled,
  nextLabel,
  pending,
}: {
  onBack?: () => void;
  onNext: () => void;
  nextDisabled?: boolean;
  nextLabel?: string;
  pending?: boolean;
}) {
  const t = useTranslations("common");
  return (
    <div className="sticky bottom-[84px] z-10 flex justify-between gap-3 bg-background/95 py-3 backdrop-blur md:bottom-0">
      {onBack ? (
        <Button variant="outline" size="lg" onClick={onBack} disabled={pending}>
          {t("back")}
        </Button>
      ) : (
        <span />
      )}
      <Button size="lg" className="min-w-40 flex-1 sm:flex-none" onClick={onNext} disabled={nextDisabled || pending}>
        {pending ? t("loading") : (nextLabel ?? t("next"))}
      </Button>
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const t = useTranslations("common");
  return (
    <div role="alert" className="flex items-center justify-between gap-4 rounded-[18px] border border-destructive/40 bg-destructive/10 p-4 text-sm">
      <span>{t("error", { message })}</span>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          {t("retry")}
        </Button>
      )}
    </div>
  );
}

export function Loading({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3 rounded-[18px] border border-dashed p-6 text-sm text-muted-foreground">
      <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-hidden />
      {text}
    </div>
  );
}
