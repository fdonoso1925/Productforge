import { describe, expect, it } from "vitest";
import { isPublicPath, LOGIN_PATH } from "./public-paths";

describe("isPublicPath", () => {
  it("deja abiertas solo el login y la política de privacidad", () => {
    expect(isPublicPath("/es/login")).toBe(true);
    expect(isPublicPath("/pt/privacy")).toBe(true);
    expect(isPublicPath("/es/privacy/")).toBe(true);
  });

  it("cierra todo lo demás, incluidos intentos de colarse", () => {
    for (const path of ["/es", "/es/history", "/es/products/1", "/es/settings", "/es/new"]) {
      expect(isPublicPath(path)).toBe(false);
    }
    for (const path of ["/es/privacy/x", "/es/login/../history", "/en/privacy", "/privacy", "/es/privacyx"]) {
      expect(isPublicPath(path)).toBe(false);
    }
  });

  it("solo el login redirige a /locale cuando ya hay sesión", () => {
    expect(LOGIN_PATH.test("/es/login")).toBe(true);
    expect(LOGIN_PATH.test("/es/privacy")).toBe(false);
  });
});
