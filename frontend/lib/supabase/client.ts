import { createBrowserClient } from "@supabase/ssr";
import { env } from "@/lib/env";
import { sessionCookieOptions } from "./session";

export function createClient() {
  return createBrowserClient(env.supabaseUrl, env.supabaseAnonKey, { cookieOptions: sessionCookieOptions() });
}
