import { getTranslations, setRequestLocale } from "next-intl/server";
import { OneDriveCard, type Outcome } from "@/components/settings/onedrive-card";
import { Link } from "@/i18n/navigation";

const OUTCOMES: Outcome[] = ["connected", "denied", "error"];

export default async function SettingsPage({ params, searchParams }: PageProps<"/[locale]/settings">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const { onedrive } = await searchParams;
  const t = await getTranslations("settings");
  const tc = await getTranslations("common");
  // Solo se aceptan los tres valores conocidos: el parámetro viene de la URL.
  const outcome = OUTCOMES.find((o) => o === onedrive) ?? null;

  return (
    <main className="mx-auto flex w-full min-w-0 max-w-3xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <nav className="flex shrink-0 gap-4 text-sm text-muted-foreground">
          <Link href="/history" className="hover:underline">
            {tc("history")}
          </Link>
          <Link href="/" className="hover:underline">
            {tc("home")}
          </Link>
        </nav>
      </header>
      <OneDriveCard outcome={outcome} />
    </main>
  );
}
