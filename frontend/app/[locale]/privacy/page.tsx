import { getTranslations, setRequestLocale } from "next-intl/server";
import { LocaleSwitch } from "@/components/locale-switch";
import { Link } from "@/i18n/navigation";
import { env } from "@/lib/env";

type Section = { title: string; items: string[] };

export default async function PrivacyPage({ params }: PageProps<"/[locale]/privacy">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("privacy");
  const tApp = await getTranslations("app");
  const sections = t.raw("sections") as Section[];

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <p className="text-sm font-medium text-muted-foreground">{tApp("name")}</p>
        <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("updated")}</p>
        <p className="mt-2">{t("intro")}</p>
        {env.contactEmail && <p className="text-sm">{t("contact", { email: env.contactEmail })}</p>}
      </header>
      {sections.map((section) => (
        <section key={section.title} className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold">{section.title}</h2>
          <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm leading-relaxed">
            {section.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ))}
      <footer className="flex items-center justify-between text-sm">
        <Link href="/" className="underline-offset-4 hover:underline">
          {t("back")}
        </Link>
        <LocaleSwitch />
      </footer>
    </main>
  );
}
