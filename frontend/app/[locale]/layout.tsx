import type { Metadata } from "next";
import { Geist_Mono, Inter, Sora } from "next/font/google";
import { notFound } from "next/navigation";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { AppShell } from "@/components/shell/app-shell";
import { routing } from "@/i18n/routing";
import "../globals.css";

const inter = Inter({ variable: "--font-sans", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const sora = Sora({ variable: "--font-sora", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Productos Aurora",
  description: "Generador de productos digitales low ticket",
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({ children, params }: LayoutProps<"/[locale]">) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);

  return (
    <html lang={locale} className={`dark ${inter.variable} ${sora.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col text-foreground">
        <NextIntlClientProvider>
          <AppShell>{children}</AppShell>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
