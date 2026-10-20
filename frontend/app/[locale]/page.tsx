import { getTranslations, setRequestLocale } from "next-intl/server";
import { LocaleSwitch } from "@/components/locale-switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { createClient } from "@/lib/supabase/server";
import { BackendStatus } from "./backend-status";
import { SignOutButton } from "./sign-out-button";

export default async function HomePage({ params }: PageProps<"/[locale]">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("home");
  const tApp = await getTranslations("app");
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const email = String(data?.claims?.email ?? "");

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-12">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">{tApp("name")}</h1>
        <div className="flex items-center gap-4">
          <LocaleSwitch />
          <SignOutButton label={t("signOut")} />
        </div>
      </header>
      <Card>
        <CardHeader>
          <CardTitle>{t("welcome", { email })}</CardTitle>
          <CardDescription>{t("comingSoon")}</CardDescription>
        </CardHeader>
        <CardContent>
          <BackendStatus
            labels={{
              checking: t("backendChecking"),
              ok: t("backendOk"),
              error: t.raw("backendError") as string,
            }}
          />
        </CardContent>
      </Card>
    </main>
  );
}
