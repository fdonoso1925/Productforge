// Solo variables públicas (NEXT_PUBLIC_*). Los secretos viven en el backend.
// Se referencian literalmente para que Next las inyecte en el bundle del cliente.
export const env = {
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
};
