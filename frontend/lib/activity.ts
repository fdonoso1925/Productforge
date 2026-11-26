// Cuántas acciones hay en curso contra el backend (generar, guardar, subir, componer…). La barra
// de actividad (components/shell/activity-indicator.tsx) se muestra mientras sea > 0. Las lecturas
// (GET) no cuentan: las pantallas tienen su propio «Cargando…» y los sondeos no deben parpadear.

type Listener = () => void;

let active = 0;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function activeCount(): number {
  return active;
}

/** Cuenta la promesa mientras dura (también si falla) y la devuelve tal cual. */
export async function track<T>(work: Promise<T>): Promise<T> {
  active += 1;
  emit();
  try {
    return await work;
  } finally {
    active = Math.max(0, active - 1);
    emit();
  }
}

/** ¿Esta petición es una acción (cambia algo) y no una lectura? */
export function isAction(init: { method?: string } = {}): boolean {
  return (init.method ?? "GET").toUpperCase() !== "GET";
}
