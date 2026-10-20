"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

type Labels = { checking: string; ok: string; error: string };
type State = { kind: "checking" } | { kind: "ok" } | { kind: "error"; status: string };

export function BackendStatus({ labels }: { labels: Labels }) {
  const [state, setState] = useState<State>({ kind: "checking" });

  useEffect(() => {
    (async () => {
      const { data } = await createClient().auth.getSession();
      const token = data.session?.access_token;
      if (!token) return setState({ kind: "error", status: "401" });
      try {
        await apiFetch("/me", token);
        setState({ kind: "ok" });
      } catch (err) {
        setState({ kind: "error", status: err instanceof ApiError ? String(err.status) : "red" });
      }
    })();
  }, []);

  const text =
    state.kind === "checking"
      ? labels.checking
      : state.kind === "ok"
        ? labels.ok
        : labels.error.replace("{status}", state.status);
  const color = state.kind === "ok" ? "bg-emerald-500" : state.kind === "error" ? "bg-destructive" : "bg-muted-foreground";

  return (
    <p className="flex items-center gap-2 text-sm">
      <span className={`size-2 rounded-full ${color}`} aria-hidden />
      {text}
    </p>
  );
}
