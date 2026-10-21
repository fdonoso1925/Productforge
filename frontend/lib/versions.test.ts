import { describe, expect, it } from "vitest";
import { buildVersionTree, flattenTree } from "./versions";

const v = (id: string, parent: string | null, day: number) => ({
  id,
  parent_product_id: parent,
  created_at: `2026-10-${String(day).padStart(2, "0")}T10:00:00Z`,
});

describe("buildVersionTree", () => {
  it("anida versiones por padre y ordena hermanos por fecha", () => {
    const tree = buildVersionTree([v("c", "a", 5), v("a", null, 1), v("b", "a", 3), v("d", "b", 4)]);
    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe("a");
    expect(tree[0].children.map((n) => n.id)).toEqual(["b", "c"]);
    expect(tree[0].children[0].children.map((n) => n.id)).toEqual(["d"]);
  });

  it("trata como raíz a quien tiene un padre que no está en la lista", () => {
    const tree = buildVersionTree([v("x", "missing", 2), v("y", null, 1)]);
    expect(tree.map((n) => n.id)).toEqual(["y", "x"]);
  });

  it("no se rompe con un ciclo ni con un nodo que es su propio padre", () => {
    const tree = buildVersionTree([v("a", "a", 1)]);
    expect(tree.map((n) => n.id)).toEqual(["a"]);
  });

  it("flattenTree da el nivel de cada nodo en orden de lectura", () => {
    const tree = buildVersionTree([v("a", null, 1), v("b", "a", 2), v("c", "b", 3), v("d", "a", 4)]);
    expect(flattenTree(tree).map(({ node, depth }) => `${depth}${node.id}`)).toEqual(["0a", "1b", "2c", "1d"]);
  });

  it("lista vacía → árbol vacío", () => {
    expect(buildVersionTree([])).toEqual([]);
  });
});
