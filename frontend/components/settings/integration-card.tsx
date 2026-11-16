"use client";

import { CheckCircle2, CircleAlert, Megaphone, ShoppingBag } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { ConfirmButton } from "@/components/product/confirm-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorBox } from "@/components/wizard/step-nav";
import { ApiError, api } from "@/lib/api";
import type { IntegrationProvider, IntegrationStatus } from "@/lib/types";

const ICONS = { meta: Megaphone, hotmart: ShoppingBag } as const;

/**
 * Conexión con Meta Ads u Hotmart: se pegan las credenciales y quedan guardadas cifradas en el
 * backend. Los valores nunca vuelven al navegador; el campo muestra solo los últimos 4 caracteres.
 * Campo vacío = «dejar como está».
 */
export function IntegrationCard({
  provider,
  status,
  onChange,
}: {
  provider: IntegrationProvider;
  status: IntegrationStatus;
  onChange: (next: IntegrationStatus) => void;
}) {
  const t = useTranslations(`settings.integrations.${provider}`);
  const tc = useTranslations("settings.integrations");
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [test, setTest] = useState<{ ok: boolean; detail: string } | null>(null);
  const Icon = ICONS[provider];

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const filled = Object.values(values).some((v) => v.trim());
  const save = () =>
    run(async () => {
      onChange(await api.saveIntegration(provider, values));
      setValues({});
      setTest(null);
      setNotice(tc("saved"));
    });
  const runTest = () =>
    run(async () => {
      setTest(await api.testIntegration(provider));
    });
  const disconnect = () =>
    run(async () => {
      await api.disconnectIntegration(provider);
      onChange(await api.integrations().then((all) => all[provider]));
      setTest(null);
    });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <Icon className="size-5" aria-hidden />
          {t("title")}
          {status.connected ? (
            <Badge>{tc("connected")}</Badge>
          ) : (
            <Badge variant="outline">{status.missing.length ? tc("incomplete", { count: status.missing.length }) : tc("notConnected")}</Badge>
          )}
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
          {(t.raw("steps") as string[]).map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>

        {!status.can_save && <ErrorBox message={tc("noKey")} />}
        {error && <ErrorBox message={error} />}

        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (filled) void save();
          }}
          autoComplete="off"
        >
          {status.fields.map((f) => (
            <div key={f.key} className="flex min-w-0 flex-col gap-1.5">
              <Label htmlFor={`${provider}-${f.key}`} className="flex flex-wrap items-center gap-2">
                {t(`fields.${f.key}`)}
                {!f.required && <span className="text-xs font-normal text-muted-foreground">{tc("optional")}</span>}
                {f.set && (
                  <span className="flex items-center gap-1 text-xs font-normal text-lavender">
                    <CheckCircle2 className="size-3.5" aria-hidden />
                    {f.source === "env" ? tc("fromEnv") : tc("saved")}
                  </span>
                )}
              </Label>
              <Input
                id={`${provider}-${f.key}`}
                type={f.secret ? "password" : "text"}
                autoComplete="off"
                spellCheck={false}
                value={values[f.key] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                placeholder={f.set ? `${f.hint ?? ""} · ${tc("keep")}` : t(`placeholders.${f.key}`)}
                disabled={busy || !status.can_save}
              />
              <p className="text-xs text-muted-foreground">{t(`hints.${f.key}`)}</p>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
            <Button type="submit" disabled={busy || !filled || !status.can_save}>
              {busy ? tc("saving") : tc("save")}
            </Button>
            <Button type="button" variant="outline" onClick={() => void runTest()} disabled={busy || !status.connected}>
              {tc("test")}
            </Button>
            {status.has_saved && (
              <ConfirmButton label={tc("disconnect")} confirmLabel={tc("disconnectConfirm")} onConfirm={() => void disconnect()} disabled={busy} />
            )}
          </div>
        </form>

        {notice && (
          <p role="status" className="text-sm text-lavender">
            {notice}
          </p>
        )}
        {test && (
          <p
            role="status"
            className={`flex items-center gap-2 rounded-lg p-3 text-sm ${test.ok ? "bg-primary/10" : "bg-destructive/10 text-destructive"}`}
          >
            {test.ok ? <CheckCircle2 className="size-4" aria-hidden /> : <CircleAlert className="size-4" aria-hidden />}
            {test.ok ? tc("testOk", { detail: test.detail }) : tc("testFail", { detail: test.detail })}
          </p>
        )}
        <p className="text-xs text-muted-foreground">{tc("securityNote")}</p>
      </CardContent>
    </Card>
  );
}
