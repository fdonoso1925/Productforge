import { createServerClient } from "@supabase/ssr";
import createIntlMiddleware from "next-intl/middleware";
import { type NextRequest, NextResponse } from "next/server";
import { routing } from "@/i18n/routing";
import { env } from "@/lib/env";
import { isPublicPath, LOGIN_PATH } from "@/lib/public-paths";

const intl = createIntlMiddleware(routing);

export async function proxy(request: NextRequest) {
  const response = intl(request);
  // next-intl redirige rutas sin idioma (/ → /es); dejamos pasar esa redirección.
  if (response.headers.get("location")) return response;

  // Refresca la sesión de Supabase y escribe las cookies nuevas en la respuesta.
  const supabase = createServerClient(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet) => {
        toSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });
  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims);

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
