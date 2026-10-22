"use client";

import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ErrorBox } from "@/components/wizard/step-nav";
import type { Proof } from "@/lib/ads";
import { ApiError, api } from "@/lib/api";

const KINDS: Proof["kind"][] = ["testimonial", "stat", "authority"];

/**
 * Pruebas REALES (testimonios, cifras, experiencia) que los anuncios pueden citar. La IA nunca las
 * inventa: sin pruebas cargadas, los ángulos de prueba social ni aparecen.
 */
export function ProofsPanel({ productId }: { productId?: string }) {
  const t = useTranslations("ads.proofs");
  const [proofs, setProofs] = useState<Proof[] | null>(null);
  const [kind, setKind] = useState<Proof["kind"]>("testimonial");
  const [text, setText] = useState("");
  const [author, setAuthor] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Sube al agregar o quitar una prueba para volver a leer la lista.
  const [nonce, setNonce] = useState(0);
  const reload = () => setNonce((n) => n + 1);

  useEffect(() => {
    let alive = true;
    api
      .adsProofs(productId)
      .then((list) => alive && setProofs(list))
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [productId, nonce]);

  const add = async () => {
    setPending(true);
    setError(null);
    try {
      await api.adsAddProof({ kind, text: text.trim(), author: author.trim() || null, product_id: productId ?? null });
      setText("");
      setAuthor("");
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  const remove = async (id: string) => {
    setError(null);
    try {
      await api.adsDeleteProof(id);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  return (
    <section className="flex flex-col gap-3 rounded-xl border p-4" aria-label={t("title")}>
      <div>
        <h3 className="font-semibold">{t("title")}</h3>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>
      {error && <ErrorBox message={error} />}
      {proofs && proofs.length > 0 && (
        <ul className="flex flex-col gap-2">
          {proofs.map((p) => (
            <li key={p.id} className="flex items-start justify-between gap-3 rounded-lg bg-muted/40 p-3 text-sm">
              <span>
                <span className="mr-2 text-xs font-medium uppercase text-muted-foreground">{t(`kinds.${p.kind}`)}</span>
                {p.text}
                {p.author && <span className="text-muted-foreground"> — {p.author}</span>}
              </span>
              <Button variant="ghost" size="icon-sm" onClick={() => remove(p.id)} aria-label={t("remove")}>
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as Proof["kind"])}
          className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
          aria-label={t("kind")}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`kinds.${k}`)}
            </option>
          ))}
        </select>
        <Input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder={t("author")} maxLength={80} />
      </div>
      <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("text")} maxLength={500} />
      <div className="flex justify-end">
        <Button variant="outline" onClick={add} disabled={pending || text.trim().length < 3}>
          {t("add")}
        </Button>
      </div>
    </section>
  );
}
