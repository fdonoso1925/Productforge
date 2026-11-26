import { describe, expect, it } from "vitest";
import { activeCount, isAction, subscribe, track } from "./activity";

describe("actividad en curso (indicador «Procesando…»)", () => {
  it("cuenta las acciones mientras duran, también si fallan", async () => {
    const seen: number[] = [];
    const off = subscribe(() => seen.push(activeCount()));
    let finish!: () => void;
    const work = track(new Promise<void>((resolve) => (finish = resolve)));
    expect(activeCount()).toBe(1);
    finish();
    await work;
    await expect(track(Promise.reject(new Error("x")))).rejects.toThrow("x");
    expect(activeCount()).toBe(0);
    expect(seen).toEqual([1, 0, 1, 0]);
    off();
  });

  it("solo las acciones encienden el indicador, no las lecturas", () => {
    expect(isAction({ method: "POST" })).toBe(true);
    expect(isAction({ method: "delete" })).toBe(true);
    expect(isAction({})).toBe(false);
    expect(isAction({ method: "GET" })).toBe(false);
  });
});
