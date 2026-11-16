import { Check, ChevronLeft } from "lucide-react";
import { Cover } from "@/components/library/cover";
import { Link } from "@/i18n/navigation";

type Stat = { value: string; label: string };

type Props = {
  backHref: string;
  backLabel: string;
  cover: { seed: string; title: string; label?: string };
  /** Etiquetas sobre el título (mercado, estado…). */
  chips?: React.ReactNode;
  title: string;
  description?: string;
  stats?: Stat[];
  includes?: { title: string; items: string[] };
  /** Acciones principales (descargar, rehacer…). */
  actions?: React.ReactNode;
};

/**
 * Cabecera de detalle del diseño «Biblioteca nocturna» (1c): volver, portada grande en un panel de
 * vidrio a la izquierda y, a la derecha, etiquetas, título, descripción, cifras, «lo que incluye» y
 * las acciones. Lo demás de cada pantalla (paneles, listas, formularios) va debajo, a todo el ancho.
 */
export function DetailHero({ backHref, backLabel, cover, chips, title, description, stats, includes, actions }: Props) {
  return (
    <section className="flex flex-col gap-5 md:gap-8">
      <Link
        href={backHref}
        className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
      >
        <ChevronLeft className="size-4" aria-hidden />
        {backLabel}
      </Link>

      <div className="grid items-start gap-6 md:gap-10 lg:grid-cols-[minmax(0,340px)_1fr] lg:gap-14">
        <div className="glass mx-auto w-full max-w-[260px] rounded-3xl p-4 shadow-[0_0_80px_rgb(245_199_107/0.12)] sm:max-w-[300px] md:p-6 lg:max-w-none">
          <Cover
            seed={cover.seed}
            title={cover.title}
            label={cover.label}
            size="lg"
            className="shadow-[0_24px_50px_rgb(3_5_20/0.6)]"
          />
        </div>

        <div className="flex min-w-0 flex-col gap-5">
          {chips && <div className="flex flex-wrap items-center gap-2">{chips}</div>}
          <h1 className="text-[30px] leading-[1.1] font-semibold md:text-5xl">{title}</h1>
          {description && <p className="max-w-[620px] text-base leading-relaxed text-muted-foreground md:text-lg">{description}</p>}

          {stats && stats.length > 0 && (
            <dl className="flex flex-wrap gap-x-9 gap-y-3 text-sm text-muted-foreground">
              {stats.map((s) => (
                <div key={s.label}>
                  <dd className="order-1 font-heading text-lg font-semibold text-foreground">{s.value}</dd>
                  <dt className="order-2">{s.label}</dt>
                </div>
              ))}
            </dl>
          )}

          {includes && includes.items.length > 0 && (
            <div className="glass max-w-[620px] rounded-[20px] p-5 md:p-6">
              <p className="mb-3.5 font-heading text-[17px] font-semibold">{includes.title}</p>
              <ul className="flex flex-col gap-3">
                {includes.items.map((item) => (
                  <li key={item} className="flex items-center gap-3 text-[15px]">
                    <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent">
                      <Check className="size-3.5 text-lavender" aria-hidden strokeWidth={2.6} />
                    </span>
                    <span className="min-w-0">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {actions && <div className="flex flex-wrap items-center gap-3.5">{actions}</div>}
        </div>
      </div>
    </section>
  );
}
