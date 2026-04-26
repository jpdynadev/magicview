import "dotenv/config";

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseArgs } from "node:util";

import { getSupabaseAdminClient } from "../src/lib/server/supabase-admin";
import { ingestScryfallCard } from "../src/lib/server/card-cache";

interface ScryfallBulkDataItem {
  type: string;
  download_uri: string;
}

interface ScryfallOracleCard {
  id: string;
  name: string;
  cmc?: number;
  type_line?: string;
  oracle_text?: string;
  color_identity?: string[];
  image_uris?: {
    normal?: string;
  };
  card_faces?: Array<{
    oracle_text?: string;
    type_line?: string;
  }>;
  digital?: boolean;
  games?: string[];
  layout?: string;
}

const DATA_DIRECTORY = path.join(process.cwd(), "data", "scryfall");
const DEFAULT_OUTPUT = path.join(DATA_DIRECTORY, "oracle-cards.json");

async function fetchOracleBulkFile(targetFile: string) {
  console.log("Fetching Scryfall bulk metadata...");
  const bulkResponse = await fetch("https://api.scryfall.com/bulk-data");
  const bulkJson = (await bulkResponse.json()) as { data: ScryfallBulkDataItem[] };
  const oracleData = bulkJson.data.find((entry) => entry.type === "oracle_cards");

  if (!oracleData) {
    throw new Error("Could not find oracle_cards bulk data from Scryfall.");
  }

  console.log(`Downloading bulk oracle data to ${targetFile} ...`);
  const cardsResponse = await fetch(oracleData.download_uri);
  const cardsJson = await cardsResponse.text();

  await mkdir(path.dirname(targetFile), { recursive: true });
  await writeFile(targetFile, cardsJson, "utf8");
}

function isCommanderRelevant(card: ScryfallOracleCard): boolean {
  return !card.digital && (card.games ?? []).includes("paper") && card.layout !== "token";
}

async function main() {
  const { values } = parseArgs({
    options: {
      file: {
        type: "string",
      },
      download: {
        type: "boolean",
        default: false,
      },
      ai: {
        type: "boolean",
        default: false,
      },
      limit: {
        type: "string",
      },
      offset: {
        type: "string",
      },
    },
  });

  const filePath = values.file ?? DEFAULT_OUTPUT;
  const limit = values.limit ? Number(values.limit) : undefined;
  const offset = values.offset ? Number(values.offset) : 0;

  if (values.download || !filePath) {
    await fetchOracleBulkFile(filePath);
  }

  const content = await readFile(filePath, "utf8");
  const cards = (JSON.parse(content) as ScryfallOracleCard[]).filter(isCommanderRelevant);
  const slice = cards.slice(offset, limit ? offset + limit : undefined);
  const supabase = getSupabaseAdminClient();

  console.log(
    `Ingesting ${slice.length} cards from ${path.relative(process.cwd(), filePath)}...`,
  );

  let completed = 0;
  for (const card of slice) {
    completed += 1;
    await ingestScryfallCard(card, {
      supabase,
      compressWithAi: values.ai,
    });

    if (completed % 100 === 0 || completed === slice.length) {
      console.log(`Processed ${completed}/${slice.length}`);
    }
  }

  console.log("Scryfall sync complete.");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
