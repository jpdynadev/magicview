function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const publicEnv = {
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
};

export function hasSupabasePublicEnv(): boolean {
  return Boolean(publicEnv.supabaseUrl && publicEnv.supabaseAnonKey);
}

export const serverEnv = {
  get supabaseUrl() {
    return required("NEXT_PUBLIC_SUPABASE_URL");
  },
  get supabaseAnonKey() {
    return required("NEXT_PUBLIC_SUPABASE_ANON_KEY");
  },
  get supabaseServiceRoleKey() {
    return required("SUPABASE_SERVICE_ROLE_KEY");
  },
  get openAiApiKey() {
    return required("OPENAI_API_KEY");
  },
  get mulliganModel() {
    return process.env.OPENAI_MULLIGAN_MODEL ?? "gpt-5.4-mini";
  },
  get cardCompressionModel() {
    return process.env.OPENAI_CARD_COMPRESSION_MODEL ?? "gpt-5.4-nano";
  },
  get handImagesBucket() {
    return process.env.SUPABASE_HAND_IMAGES_BUCKET ?? "hand-images";
  },
};
