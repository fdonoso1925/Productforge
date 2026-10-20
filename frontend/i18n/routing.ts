import { defineRouting } from "next-intl/routing";

// Idioma de la INTERFAZ (español por defecto, portugués opcional).
// El mercado del contenido generado (pt-BR / es-LATAM) es otra cosa y se elige en el wizard.
export const routing = defineRouting({
  locales: ["es", "pt"],
  defaultLocale: "es",
});

export type Locale = (typeof routing.locales)[number];
