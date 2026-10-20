import { getTranslations, setRequestLocale } from "next-intl/server";
import { LocaleSwitch } from "@/components/locale-switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { safeNextPath } from "@/lib/redirect";
import { GoogleButton } from "./google-button";

export default async function LoginPage({ params, searchParams }: PageProps<"/[locale]/login">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const { next, error } = await searchParams;
  const t = await getTranslations("login");
  const tApp = await getTranslations("app");

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-16">
      <div className="text-center">
        <h1 className="text-3xl font-semibold tracking-tight">{tApp("name")}</h1>
        <p className="mt-2 text-muted-foreground">{tApp("tagline")}</p>
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("subtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {t("error")}
            </p>
          )}
          <GoogleButton
            label={t("google")}
            next={safeNextPath(typeof next === "string" ? next : null, `/${locale}`)}
          />
        </CardContent>
      </Card>
      <LocaleSwitch />
    </main>
  );
}
