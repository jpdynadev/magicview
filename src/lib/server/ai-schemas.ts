export const cardCompressionJsonSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    compact_summary: {
      type: "string",
      description: "One sentence summary of the card in Commander terms.",
    },
    primary_abilities: {
      type: "array",
      items: { type: "string" },
      maxItems: 4,
    },
    secondary_abilities: {
      type: "array",
      items: { type: "string" },
      maxItems: 4,
    },
    strategic_tags: {
      type: "array",
      items: { type: "string" },
      maxItems: 8,
    },
    mulligan_relevance_score: {
      type: "integer",
      minimum: 1,
      maximum: 10,
    },
  },
  required: [
    "compact_summary",
    "primary_abilities",
    "secondary_abilities",
    "strategic_tags",
    "mulligan_relevance_score",
  ],
} as const;

export const mulliganDecisionJsonSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    decision: {
      type: "string",
      enum: ["KEEP", "MULLIGAN"],
    },
    confidence: {
      type: "number",
      minimum: 0,
      maximum: 1,
    },
    reasoning: {
      type: "array",
      minItems: 2,
      maxItems: 5,
      items: {
        type: "string",
      },
    },
    turn_plan: {
      type: "object",
      additionalProperties: false,
      properties: {
        turn_1: { type: "string" },
        turn_2: { type: "string" },
        turn_3: { type: "string" },
      },
      required: ["turn_1", "turn_2", "turn_3"],
    },
  },
  required: ["decision", "confidence", "reasoning", "turn_plan"],
} as const;

