import { describe, expect, it } from "vitest";
import { adsManagerUrl, known, KNOWN_STATUSES, periodQuery, statusTone } from "./campaigns";

describe("campañas de Meta", () => {
  it("arma el período como preset o como rango de fechas", () => {
    expect(periodQuery("last_30d", "", "")).toBe("preset=last_30d");
    expect(periodQuery("custom", "2026-01-01", "2026-03-31")).toBe("since=2026-01-01&until=2026-03-31");
  });

  it("enlaza la campaña en Ads Manager sin el prefijo act_", () => {
    const url = new URL(adsManagerUrl("act_123", "456"));
    expect(url.hostname).toBe("adsmanager.facebook.com");
    expect(url.searchParams.get("act")).toBe("123");
    expect(url.searchParams.get("selected_campaign_ids")).toBe("456");
  });

  it("da un tono a cada estado y reconoce solo los estados conocidos", () => {
    expect(statusTone("ACTIVE")).toBe("default");
    expect(statusTone("WITH_ISSUES")).toBe("destructive");
    expect(statusTone("DELETED")).toBe("outline");
    expect(statusTone("PAUSED")).toBe("secondary");
    expect(known(KNOWN_STATUSES, "PAUSED")).toBe(true);
    expect(known(KNOWN_STATUSES, "RARO")).toBe(false);
  });
});
