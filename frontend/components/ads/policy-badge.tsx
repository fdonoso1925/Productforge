"use client";

import { AlertTriangle, CheckCircle2, OctagonX } from "lucide-react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import type { PolicyStatus } from "@/lib/ads";

const STYLE: Record<PolicyStatus, string> = {
  green: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  yellow: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  red: "bg-destructive/10 text-destructive",
};
const ICON = { green: CheckCircle2, yellow: AlertTriangle, red: OctagonX } as const;

/** Semáforo de políticas de Meta: color, ícono y texto (nunca solo color). */
export function PolicyBadge({ status }: { status: PolicyStatus | null }) {
  const t = useTranslations("ads.policy");
  if (!status) return null;
  const Icon = ICON[status];
  return (
    <Badge variant="outline" className={`border-transparent ${STYLE[status]}`} title={t(`${status}Hint`)}>
      <Icon aria-hidden />
      {t(status)}
    </Badge>
  );
}
