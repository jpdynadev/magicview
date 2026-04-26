interface OutputMessageContent {
  type?: string;
  text?: string;
}

interface OutputMessage {
  content?: OutputMessageContent[];
}

interface ResponseShape {
  output_text?: string;
  output?: OutputMessage[];
}

export function getStructuredOutputText(response: unknown): string {
  const typed = response as ResponseShape;

  if (typed.output_text) {
    return typed.output_text;
  }

  const parts =
    typed.output?.flatMap((item) =>
      (item.content ?? [])
        .filter((content) => content.type === "output_text" && content.text)
        .map((content) => content.text as string),
    ) ?? [];

  if (!parts.length) {
    throw new Error("OpenAI returned no structured output text.");
  }

  return parts.join("\n");
}

