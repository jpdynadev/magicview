export const serverEnv = {
  get openAiApiKey() {
    const value = process.env.OPENAI_API_KEY;
    if (!value) {
      throw new Error("Missing required environment variable: OPENAI_API_KEY");
    }
    return value;
  },
  get mulliganModel() {
    return process.env.OPENAI_MULLIGAN_MODEL ?? "gpt-5.4-mini";
  },
  get cardCompressionModel() {
    return process.env.OPENAI_CARD_COMPRESSION_MODEL ?? "gpt-5.4-nano";
  },
};
