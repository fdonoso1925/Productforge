/**
 * Devuelve una ruta interna segura para redirigir tras el login.
 * Evita open redirects (`//evil.com`, `https://…`, `/\evil.com`).
 */
export function safeNextPath(next: string | null | undefined, fallback = "/"): string {
  if (!next || next.length > 512) return fallback;
  if (!next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  if (/[\u0000-\u001f]/.test(next)) return fallback;
  return next;
}
