"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

export function GoogleButton({ label, next }: { label: string; next: string }) {
  const [pending, setPending] = useState(false);

  async function signIn() {
    setPending(true);
    const redirectTo = `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;
    const { error } = await createClient().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo },
    });
    if (error) setPending(false);
  }

  return (
    <Button size="lg" onClick={signIn} disabled={pending}>
      {label}
    </Button>
  );
}
