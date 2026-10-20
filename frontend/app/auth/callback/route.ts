import { type NextRequest, NextResponse } from "next/server";
import { routing } from "@/i18n/routing";
import { safeNextPath } from "@/lib/redirect";
import { createClient } from "@/lib/supabase/server";

// Callback de OAuth (Google → Supabase → aquí). Canjea el código por la sesión.
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const next = safeNextPath(searchParams.get("next"), `/${routing.defaultLocale}`);
  const locale = next.split("/")[1] === "pt" ? "pt" : routing.defaultLocale;
  const code = searchParams.get("code");

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(`${origin}${next}`);
  }
  // Sin código o con error (p. ej. email no autorizado: el trigger rechaza el alta).
  return NextResponse.redirect(`${origin}/${locale}/login?error=1`);
}
