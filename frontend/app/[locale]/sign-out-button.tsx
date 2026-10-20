"use client";

import { Button } from "@/components/ui/button";
import { useRouter } from "@/i18n/navigation";
import { createClient } from "@/lib/supabase/client";

export function SignOutButton({ label }: { label: string }) {
  const router = useRouter();

  async function signOut() {
    await createClient().auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  return (
    <Button variant="outline" size="sm" onClick={signOut}>
      {label}
    </Button>
  );
}
