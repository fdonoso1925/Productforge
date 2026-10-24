import { getTranslations, setRequestLocale } from "next-intl/server";
import { LocaleSwitch } from "@/components/locale-switch";
import { DriveCard, type Outcome } from "@/components/settings/drive-card";
import { SignOutButton } from "../sign-out-button";

const OUTCOMES: Outcome[] = ["connected", "denied", "error"];

export default async function SettingsPage({ params, searchParams }: PageProps<"/[locale]/settings">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const { drive } = await searchParams;
  const t = await getTranslations("settings");
  const th = await getTranslations("home");
  // Solo se aceptan los tres valores conocidos: el parámetro viene de la URL.
  const outcome = OUTCOMES.find((o) => o === drive) ?? null;

  return (
    <main className="mx-auto flex w-full min-w-0 max-w-3xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
      <header>
        <h1 className="text-[26px] font-bold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </header>
      <DriveCard outcome={outcome} />
      <section className="flex items-center justify-between gap-4 rounded-[20px] bg-card p-5 md:hidden">
        <LocaleSwitch />
        <SignOutButton label={th("signOut")} />
      </section>
    </main>
  );
}
