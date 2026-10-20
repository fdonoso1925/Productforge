"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

export function PasswordForm({ next }: { next: string }) {
  const t = useTranslations("login");
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function signIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setFailed(false);
    const { error } = await createClient().auth.signInWithPassword({
      email: String(form.get("email") ?? "").trim(),
      password: String(form.get("password") ?? ""),
    });
    if (error) {
      // Mensaje genérico: no revela si el email existe.
      setFailed(true);
      setPending(false);
      return;
    }
    // Navegación completa para que el proxy lea la cookie de sesión recién creada.
    window.location.assign(next);
  }

  return (
    <form onSubmit={signIn} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="email">{t("email")}</Label>
        <Input id="email" name="email" type="email" autoComplete="email" required maxLength={254} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">{t("password")}</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={128}
        />
      </div>
      {failed && (
        <p role="alert" className="text-sm text-destructive">
          {t("error")}
        </p>
      )}
      <Button type="submit" size="lg" disabled={pending}>
        {pending ? t("signingIn") : t("submit")}
      </Button>
    </form>
  );
}
