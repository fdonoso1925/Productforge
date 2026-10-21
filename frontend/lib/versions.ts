// Árbol de versiones de un producto: el original y sus remodelados / duplicados.

export type VersionRow = {
  id: string;
  parent_product_id: string | null;
  created_at: string;
};

export type VersionNode<T extends VersionRow> = T & { children: VersionNode<T>[] };

/**
 * Arma el árbol a partir de filas planas. Un nodo cuyo padre no está en la lista (p. ej. si el
 * padre es de otro usuario o se borró) se trata como raíz, así nunca se pierde una versión.
 * Los hermanos quedan ordenados del más antiguo al más nuevo.
 */
export function buildVersionTree<T extends VersionRow>(rows: T[]): VersionNode<T>[] {
  const nodes = new Map<string, VersionNode<T>>();
  for (const row of rows) nodes.set(row.id, { ...row, children: [] });

  const roots: VersionNode<T>[] = [];
  for (const node of nodes.values()) {
    const parent = node.parent_product_id ? nodes.get(node.parent_product_id) : undefined;
    // Evita ciclos corruptos (un nodo no puede ser su propio ancestro).
    if (parent && parent.id !== node.id) parent.children.push(node);
    else roots.push(node);
  }

  const byDate = (a: VersionRow, b: VersionRow) => a.created_at.localeCompare(b.created_at);
  const sort = (list: VersionNode<T>[]) => {
    list.sort(byDate);
    for (const node of list) sort(node.children);
  };
  sort(roots);
  return roots;
}

/** Recorrido en profundidad con el nivel de cada nodo (para indentar). */
export function flattenTree<T extends VersionRow>(
  roots: VersionNode<T>[],
): { node: VersionNode<T>; depth: number }[] {
  const out: { node: VersionNode<T>; depth: number }[] = [];
  const walk = (list: VersionNode<T>[], depth: number) => {
    for (const node of list) {
      out.push({ node, depth });
      walk(node.children, depth + 1);
    }
  };
  walk(roots, 0);
  return out;
}
