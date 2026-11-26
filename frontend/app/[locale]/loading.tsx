import { getTranslations } from "next-intl/server";

// Se muestra apenas se navega a otra pantalla, mientras carga (convención loading.js de Next).
export default async function Loading() {
  const t = await getTranslations("common");
  return (
    <main className="flex flex-1 items-center justify-center px-5 py-24" aria-busy="true">
      <div role="status" className="flex flex-col items-center gap-3 text-muted-foreground">
        <span className="size-9 animate-spin rounded-full border-[3px] border-primary border-t-transparent" aria-hidden />
        <span className="text-sm font-semibold">{t("loading")}</span>
      </div>
    </main>
  );
}
