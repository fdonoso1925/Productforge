/** Campañas de Meta con métricas, leídas en vivo de la cuenta (solo lectura). */

export type CampaignMetrics = {
  spend: number;
  impressions: number;
  clicks: number;
  landing_views: number;
  checkouts: number;
  purchases: number;
  revenue: number;
  ctr: number | null;
  cpc: number | null;
  cpm: number | null;
  cpa: number | null;
  roas: number | null;
  reach: number | null;
  frequency: number | null;
};

export type Campaign = {
  id: string;
  name: string;
  status: string;
  objective: string | null;
  created_time: string | null;
  budget: { kind: "daily" | "lifetime"; amount: number } | null;
  from_app: boolean;
  metrics: CampaignMetrics;
};

export type CampaignList = {
  account: { id: string; name: string; currency: string };
  fetched_at: string;
  campaigns: Campaign[];
  totals: CampaignMetrics;
};

export type CampaignDetail = {
  id: string;
  daily: ({ day: string } & CampaignMetrics)[];
  ads: { id: string; name: string; adset: string; metrics: CampaignMetrics }[];
};

export const CAMPAIGN_PRESETS = ["last_7d", "last_30d", "last_90d", "maximum", "custom"] as const;
export type CampaignPreset = (typeof CAMPAIGN_PRESETS)[number];

/** Parámetros del período para la API: un preset o un rango de fechas `YYYY-MM-DD`. */
export function periodQuery(preset: CampaignPreset, from: string, to: string): string {
  const q = new URLSearchParams();
  if (preset === "custom") {
    q.set("since", from);
    q.set("until", to);
  } else q.set("preset", preset);
  return q.toString();
}

/** Enlace a la campaña en Ads Manager (para activarla, editarla o verla allí). */
export function adsManagerUrl(accountId: string, campaignId: string): string {
  const act = accountId.replace(/^act_/, "");
  const q = new URLSearchParams({ act, selected_campaign_ids: campaignId });
  return `https://adsmanager.facebook.com/adsmanager/manage/campaigns?${q}`;
}

/** Estados que conocemos (con texto propio); el resto se muestra tal cual. */
export const KNOWN_STATUSES = ["ACTIVE", "PAUSED", "DELETED", "ARCHIVED", "IN_PROCESS", "WITH_ISSUES"] as const;
export const KNOWN_OBJECTIVES = [
  "OUTCOME_SALES",
  "OUTCOME_TRAFFIC",
  "OUTCOME_ENGAGEMENT",
  "OUTCOME_LEADS",
  "OUTCOME_AWARENESS",
  "OUTCOME_APP_PROMOTION",
] as const;

export function statusTone(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "ACTIVE") return "default";
  if (status === "WITH_ISSUES") return "destructive";
  if (status === "DELETED" || status === "ARCHIVED") return "outline";
  return "secondary";
}

export function known<T extends string>(list: readonly T[], value: string | null): value is T {
  return value !== null && (list as readonly string[]).includes(value);
}
