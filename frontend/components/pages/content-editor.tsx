"use client";

import { useTranslations } from "next-intl";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { editableLeaves, flaggedPaths, type PageContent, type SimilarityReport, sectionOf, setLeaf } from "@/lib/pages";

/**
 * Editor de todos los textos de la página, agrupados por sección. Lo que el sistema completa solo
 * (precio, garantía, urgencia, pruebas) no se edita aquí. Los textos que el detector marcó como
 * parecidos a la página modelo se resaltan.
 */
export function ContentEditor({
  content,
  similarity,
  onChange,
}: {
  content: PageContent;
  similarity: SimilarityReport | null;
  onChange: (next: PageContent) => void;
}) {
  const t = useTranslations("pages.editor");
  const flagged = flaggedPaths(similarity);
  const sections = new Map<string, ReturnType<typeof editableLeaves>>();
  for (const leaf of editableLeaves(content)) {
    const key = sectionOf(leaf.path);
    sections.set(key, [...(sections.get(key) ?? []), leaf]);
  }

  const label = (path: string) => {
    const parts = path.split(".");
    const name = [...parts].reverse().find((p) => !/^\d+$/.test(p)) ?? path;
    const index = parts.filter((p) => /^\d+$/.test(p)).map((p) => Number(p) + 1);
    const base = t.has(`fields.${name}`) ? t(`fields.${name}`) : name;
    return index.length ? `${base} ${index.join(".")}` : base;
  };

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-muted-foreground">{t("hint")}</p>
      {[...sections.entries()].map(([section, leaves]) => (
        <fieldset key={section} className="flex flex-col gap-3 rounded-xl border p-4">
          <legend className="px-1 text-sm font-semibold">{t.has(`sections.${section}`) ? t(`sections.${section}`) : section}</legend>
          {leaves.map((leaf) => {
            const id = `pe-${leaf.path}`;
            const copied = flagged.has(leaf.path);
            const common = {
              id,
              value: leaf.value,
              onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
                onChange(setLeaf(content, leaf.path, e.target.value)),
              "aria-invalid": copied || undefined,
              className: copied ? "border-amber-500" : undefined,
            };
            return (
              <div key={leaf.path} className="flex flex-col gap-1">
                <Label htmlFor={id}>{label(leaf.path)}</Label>
                {leaf.multiline ? <Textarea rows={3} {...common} /> : <Input {...common} />}
                {copied && <p className="text-xs text-amber-600">{t("similar")}</p>}
              </div>
            );
          })}
        </fieldset>
      ))}
    </div>
  );
}
