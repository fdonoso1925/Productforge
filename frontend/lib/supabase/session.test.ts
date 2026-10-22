import { describe, expect, it } from "vitest";
import { authState, hasAuthCookie, SESSION_MAX_AGE, sessionCookieOptions } from "./session";

describe("authState", () => {
  it("con claims hay sesión", () => {
    expect(authState({ data: { claims: {} }, error: null })).toBe("signed-in");
  });

  it("sin datos y sin error: no hay sesión (nunca inició o cerró)", () => {
    expect(authState({ data: null, error: null })).toBe("signed-out");
  });

  it("un token inválido o un refresh token ya usado: no hay sesión", () => {
    expect(authState({ data: null, error: { name: "AuthInvalidJwtError", status: 401 } })).toBe("signed-out");
    expect(authState({ data: null, error: { name: "AuthApiError", status: 400 } })).toBe("signed-out");
    expect(authState({ data: null, error: { name: "AuthSessionMissingError", status: 400 } })).toBe("signed-out");
  });

  it("un fallo de red o de Supabase NO se confunde con «sin sesión»", () => {
    expect(authState({ data: null, error: { name: "AuthRetryableFetchError", status: 0 } })).toBe("unknown");
    expect(authState({ data: null, error: { name: "AuthApiError", status: 503 } })).toBe("unknown");
    expect(authState({ data: null, error: { name: "AuthUnknownError" } })).toBe("unknown");
    expect(authState({ data: null, error: { status: 0 } })).toBe("unknown");
  });
});

describe("hasAuthCookie", () => {
  it("reconoce la cookie de sesión, entera o en trozos", () => {
    expect(hasAuthCookie(["sb-abc123-auth-token"])).toBe(true);
    expect(hasAuthCookie(["x", "sb-abc123-auth-token.0", "sb-abc123-auth-token.1"])).toBe(true);
  });

  it("ignora otras cookies", () => {
    expect(hasAuthCookie([])).toBe(false);
    expect(hasAuthCookie(["NEXT_LOCALE", "sb-abc123-auth-token-code-verifier", "theme"])).toBe(false);
  });
});

describe("sessionCookieOptions", () => {
  it("la sesión dura 400 días, en toda la app y sin enviarse a otros sitios", () => {
    const options = sessionCookieOptions();
    expect(options.maxAge).toBe(SESSION_MAX_AGE);
    expect(SESSION_MAX_AGE).toBe(34_560_000);
    expect(options.path).toBe("/");
    expect(options.sameSite).toBe("lax");
  });
});
