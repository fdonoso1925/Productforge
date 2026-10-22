import { createServerClient } from "@supabase/ssr";
import createIntlMiddleware from "next-intl/middleware";
import { type NextRequest, NextResponse } from "next/server";
import { routing } from "@/i18n/routing";
import { env } from "@/lib/env";
import { isPublicPath, LOGIN_PATH } from "@/lib/public-paths";
import { authState, hasAuthCookie, sessionCookieOptions } from "@/lib/supabase/session";

const intl = createIntlMiddleware(routing);

export async function proxy(request: NextRequest) {
  const response = intl(request);
  // next-intl redirige rutas sin idioma (/ → /es); dejamos pasar esa redirección.
  if (response.headers.get("location")) return response;

  // Refresca la sesión de Supabase y escribe las cookies nuevas en la respuesta.
  const supabase = createServerClient(env.supabaseUrl, env.supabaseAnonKey, {
    cookieOptions: sessionCookieOptions(),
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet) => {
        toSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });
  const hadCookie = hasAuthCookie(request.cookies.getAll().map((c) => c.name));
  let claims = await supabase.auth.getClaims();
  let state = authState(claims);
  if (state === "unknown") {
    // Supabase no respondió (red, lentitud): se reintenta una vez antes de dudar de la sesión.
    await new Promise((resolve) => setTimeout(resolve, 300));
    claims = await supabase.auth.getClaims();
    state = authState(claims);
  }
  if (hadCookie && state !== "signed-in") {
    // Diagnóstico: por qué una sesión con cookie dejó de valer (sin tokens ni datos personales).
    console.warn("[auth] sesión con cookie no verificada", {
      state,
      error: claims.error?.name,
      status: claims.error?.status,
      message: claims.error?.message?.slice(0, 120),
    });
  }
  // Un fallo de red NO es «sin sesión»: con la cookie presente se deja pasar. Es solo la puerta
  // de la interfaz; el backend y RLS siguen exigiendo un token válido en cada dato.
  const signedIn =
    state === "signed-in" || (state === "unknown" && hadCookie);

  const { pathname } = request.nextUrl;
  const locale = pathname.split("/")[1] || routing.defaultLocale;

  if (!signedIn && !isPublicPath(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = `/${locale}/login`;
    url.search = `?next=${encodeURIComponent(pathname)}`;
    return NextResponse.redirect(url);
  }
  if (signedIn && LOGIN_PATH.test(pathname)) {
    return NextResponse.redirect(new URL(`/${locale}`, request.url));
  }
  return response;
}

export const config = {
  // Excluye la API interna, assets y archivos con extensión.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
