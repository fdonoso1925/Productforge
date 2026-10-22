// Sesión de Supabase en cookies. La app es de uso personal: la sesión se recuerda mucho tiempo y
// se renueva sola (el proxy refresca el acceso con el refresh token en cada navegación).

/** Cuánto dura la cookie de sesión: 400 días, el máximo que aceptan los navegadores. */
export const SESSION_MAX_AGE = 400 * 24 * 60 * 60;

/** Mismas opciones en el cliente del navegador, el del servidor y el del proxy. */
export function sessionCookieOptions() {
  return {
    maxAge: SESSION_MAX_AGE,
    path: "/",
    sameSite: "lax" as const,
    // En http://localhost (desarrollo) una cookie `secure` no se guardaría.
    secure: process.env.NODE_ENV === "production",
  };
}

type AuthResult = { data: unknown | null; error: { name?: string; status?: number } | null };
export type AuthState = "signed-in" | "signed-out" | "unknown";

/**
 * ¿Hay sesión? Distingue «no hay sesión» de «no pude comprobarlo» (red caída, Supabase lento):
 * lo segundo no debe mandar al login a alguien con una sesión válida.
 */
export function authState({ data, error }: AuthResult): AuthState {
  if (data) return "signed-in";
  if (!error) return "signed-out";
  const transient =
    error.name === "AuthRetryableFetchError" ||
    error.name === "AuthUnknownError" ||
    error.status === 0 ||
    (error.status !== undefined && error.status >= 500);
  return transient ? "unknown" : "signed-out";
}

/** ¿Alguna cookie es de la sesión de Supabase? (`sb-<proyecto>-auth-token`, también en trozos `.0`, `.1`) */
export function hasAuthCookie(names: string[]): boolean {
  return names.some((name) => /^sb-.+-auth-token(\.\d+)?$/.test(name));
}
