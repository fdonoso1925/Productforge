import { cn } from "cn";

/** Portadas del diseño «Biblioteca nocturna»: cielo en degradé con una luna (orbe) en la esquina. */
const PALETTES = [
  { bg: "linear-gradient(160deg,#2b2f7a,#0f1440)", orb: "#f5c76b" },
  { bg: "linear-gradient(160deg,#4b2a7a,#1a0f40)", orb: "#c9a8ff" },
  { bg: "linear-gradient(160deg,#1f5a7a,#0b2540)", orb: "#8fe3ff" },
  { bg: "linear-gradient(160deg,#7a2b5e,#2a0f35)", orb: "#ffb3d9" },
  { bg: "linear-gradient(160deg,#2b6b5a,#0b2a2e)", orb: "#9ff0c8" },
];

/** Misma portada para el mismo producto (el color sale de su id, no del azar). */
export function paletteFor(seed: string) {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTES[h % PALETTES.length];
}

type Props = {
  seed: string;
  title: string;
  label?: string;
  className?: string;
  /** Tamaño del título: «sm» para miniaturas, «lg» para el detalle. */
  size?: "sm" | "md" | "lg";
  children?: React.ReactNode;
};

export function Cover({ seed, title, label, className, size = "md", children }: Props) {
  const { bg, orb } = paletteFor(seed);
  const orbSize = size === "sm" ? "size-10 -top-3 -right-3" : size === "lg" ? "size-44 -top-11 -right-11" : "size-24 -top-6 -right-6";
  const text = size === "sm" ? "text-sm" : size === "lg" ? "text-2xl md:text-4xl" : "text-[19px]";
  return (
    <div
      className={cn(
        "relative flex aspect-[3/4] flex-col justify-end overflow-hidden rounded-[14px]",
        size === "sm" ? "p-3" : size === "lg" ? "p-5 md:p-8" : "p-[18px]",
        className,
      )}
      style={{ background: bg }}
    >
      <div
        aria-hidden
        className={cn("absolute rounded-full opacity-90", orbSize)}
        style={{ background: `radial-gradient(circle at 35% 35%,#fff6dc,${orb})` }}
      />
      {label && (
        <span className="relative mb-1.5 text-[11px] font-semibold tracking-[0.12em] text-[#d4d1ff] uppercase">{label}</span>
      )}
      <span className={cn("relative line-clamp-4 font-heading leading-[1.15] font-semibold", text)}>{title}</span>
      {children}
    </div>
  );
}
