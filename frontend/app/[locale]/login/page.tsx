import { getTranslations, setRequestLocale } from "next-intl/server";
import { LocaleSwitch } from "@/components/locale-switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "@/i18n/navigation";
import { safeNextPath } from "@/lib/redirect";
import { PasswordForm } from "./password-form";

export default async function LoginPage({ params, searchParams }: PageProps<"/[locale]/login">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const { next } = await searchParams;
  const t = await getTranslations("login");
  const tApp = await getTranslations("app");

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-16">
      <div className="text-center">
        <h1 className="text-3xl font-bold">{tApp("name")}</h1>
        <p className="mt-2 text-muted-foreground">{tApp("tagline")}</p>
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("subtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <PasswordForm next={safeNextPath(typeof next === "string" ? next : null, `/${locale}`)} />
        </CardContent>
      </Card>
      <div className="flex items-center gap-4">
        <LocaleSwitch />
        <Link href="/privacy" className="text-sm text-muted-foreground underline-offset-4 hover:underline">
          {t("privacy")}
        </Link>
      </div>
    </main>
  );
}
