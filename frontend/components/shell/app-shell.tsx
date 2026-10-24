"use client";

import { History, Home, type LucideIcon, Megaphone, PackagePlus, Plus, Settings, ShoppingBag, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { LocaleSwitch } from "@/components/locale-switch";
import { Link, usePathname } from "@/i18n/navigation";
import { SignOutButton } from "@/app/[locale]/sign-out-button";

const PUBLIC = /^\/(login|privacy)\/?$/;

type Tab = { href: string; label: string; icon: LucideIcon; active: boolean };

/**
 * Marco de la app (diseño «Creator App»): sidebar de 220 px en escritorio, tab bar de 84 px con «+»
 * central en móvil. El botón «+» abre un menú (escritorio) o una hoja inferior (móvil) con lo que
 * se puede crear. Login y privacidad se muestran sin marco.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("shell");
  const tc = useTranslations("common");
  const th = useTranslations("home");
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [lastPath, setLastPath] = useState(pathname);
  const firstOption = useRef<HTMLAnchorElement>(null);

  // Cerrar el menú al navegar (se ajusta durante el render, sin efecto).
  if (lastPath !== pathname) {
    setLastPath(pathname);
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (PUBLIC.test(pathname)) return <>{children}</>;

  const tabs: Tab[] = [
    { href: "/", label: tc("home"), icon: Home, active: pathname === "/" },
    { href: "/history", label: tc("history"), icon: History, active: pathname.startsWith("/history") },
    { href: "/ads", label: t("createAds"), icon: Megaphone, active: pathname.startsWith("/ads") },
    { href: "/settings", label: tc("settings"), icon: Settings, active: pathname.startsWith("/settings") },
    // Solo en la barra lateral: la barra inferior del móvil usa los cuatro primeros.
    { href: "/hotmart", label: t("hotmart"), icon: ShoppingBag, active: pathname.startsWith("/hotmart") },
  ];

  const options = [
    { href: "/new", title: t("createPackage"), hint: t("createPackageHint"), icon: PackagePlus, accent: false },
    { href: "/ads/new", title: t("createAds"), hint: t("createAdsHint"), icon: Megaphone, accent: true },
  ];

  const menu = (
    <ul className="flex flex-col gap-2.5">
      {options.map((o, i) => (
        <li key={o.href}>
          <Link
            href={o.href}
            ref={i === 0 ? firstOption : undefined}
            className={`flex items-center gap-3 rounded-[18px] p-4 text-left ${
              o.accent ? "bg-primary text-primary-foreground" : "bg-card text-foreground hover:bg-secondary"
            }`}
          >
            <o.icon className="size-5 shrink-0" aria-hidden />
            <span className="flex min-w-0 flex-col">
              <span className="text-base font-bold">{o.title}</span>
              <span className={`text-[13px] ${o.accent ? "" : "text-muted-foreground"}`}>{o.hint}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );

  return (
    <>
      {/* Sidebar (escritorio) */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-[220px] flex-col gap-1.5 border-r bg-sidebar px-3.5 py-5 md:flex">
        <div className="px-2.5 pb-3.5 text-xl font-bold tracking-tight">{t("brand")}</div>
        <div className="relative mb-3">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-haspopup="dialog"
            className="flex h-[46px] w-full items-center justify-center gap-2 rounded-full bg-primary text-[15px] font-bold text-primary-foreground hover:bg-primary/85"
          >
            <Plus className="size-4" aria-hidden />
            {t("create")}
          </button>
          {open && (
            <div
              role="dialog"
              aria-label={t("createTitle")}
              className="absolute top-14 left-0 z-40 hidden w-[320px] rounded-[22px] border bg-background p-3 shadow-2xl md:block"
            >
              <p className="px-1 pb-2.5 text-lg font-bold tracking-tight">{t("createTitle")}</p>
              {menu}
            </div>
          )}
        </div>
        <nav aria-label={t("main")} className="flex flex-col gap-1.5">
          {tabs.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={tab.active ? "page" : undefined}
              className={`flex items-center gap-2.5 rounded-xl p-3 text-[15px] font-bold ${
                tab.active ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <tab.icon className="size-[18px]" aria-hidden />
              {tab.label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto flex items-center justify-between gap-2 px-1">
          <LocaleSwitch />
          <SignOutButton label={th("signOut")} />
        </div>
      </aside>
      {/* El velo va POR DEBAJO del sidebar (z-20): el menú vive dentro del sidebar y, si el velo
          lo tapara, cada clic en una opción cerraría el menú sin llegar al enlace. */}
      {open && <div className="fixed inset-0 z-10 hidden bg-black/40 md:block" onClick={() => setOpen(false)} aria-hidden />}

      <div className="flex min-w-0 flex-1 flex-col pb-[84px] md:pb-0 md:pl-[220px]">{children}</div>

      {/* Tab bar (móvil) */}
      <nav
        aria-label={t("main")}
        className="fixed inset-x-0 bottom-0 z-20 grid h-[84px] grid-cols-5 items-start border-t bg-background/95 px-1 pt-2 backdrop-blur md:hidden"
      >
        {[tabs[0], tabs[1]].map((tab) => (
          <TabLink key={tab.href} tab={tab} />
        ))}
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-label={t("create")}
            aria-haspopup="dialog"
            className="-mt-[18px] flex size-[54px] items-center justify-center rounded-full border-4 border-background bg-primary text-primary-foreground"
          >
            <Plus className="size-7" aria-hidden />
          </button>
        </div>
        {[tabs[2], tabs[3]].map((tab) => (
          <TabLink key={tab.href} tab={tab} />
        ))}
      </nav>

      {/* Hoja inferior (móvil) */}
      {open && (
        <div className="md:hidden">
          <div className="fixed inset-0 z-40 bg-black/60" onClick={() => setOpen(false)} aria-hidden />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t("createTitle")}
            className="fixed inset-x-0 bottom-0 z-50 rounded-t-[28px] border-t bg-background px-5 pt-3 pb-9"
          >
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-input" aria-hidden />
            <div className="mb-3.5 flex items-center justify-between">
              <p className="text-[22px] font-bold tracking-tight">{t("createTitle")}</p>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label={t("close")}
                className="flex size-10 items-center justify-center rounded-full bg-card"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
            {menu}
          </div>
        </div>
      )}
    </>
  );
}

function TabLink({ tab }: { tab: Tab }) {
  return (
    <Link
      href={tab.href}
      aria-current={tab.active ? "page" : undefined}
      className={`flex flex-col items-center gap-1 rounded-xl px-1 py-1.5 text-xs font-bold ${
        tab.active ? "text-foreground" : "text-[#6f6d66] hover:text-foreground"
      }`}
    >
      <tab.icon className={`size-5 ${tab.active ? "text-primary" : ""}`} aria-hidden />
      <span className="max-w-full truncate">{tab.label}</span>
    </Link>
  );
}
