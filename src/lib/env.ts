function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function requiredAny(names: string[]): string {
  for (const name of names) {
    const value = process.env[name];
    if (value) {
      return value;
    }
  }

  throw new Error(
    `Missing required environment variable. Set one of: ${names.join(", ")}`,
  );
}

export const serverEnv = {
  get databaseUrl() {
    return requiredAny([
      "DATABASE_URL",
      "NETLIFY_DATABASE_URL",
      "POSTGRES_URL",
      "NEON_DATABASE_URL",
    ]);
  },
  get jwtSecret() {
    return required("MAGICVIEW_JWT_SECRET");
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
};
