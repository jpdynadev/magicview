import fs from 'node:fs';
import { neon } from '@neondatabase/serverless';

// Temporary throwaway Neon project used only as a result bus for this isolated
// engine-test branch. The project is deleted immediately after diagnostics are read.
const url = process.env.FORGE_RESULT_DATABASE_URL || 'postgresql://neondb_owner:npg_rOoWzTHv35Cb@ep-muddy-shadow-af24ktw5-pooler.c-2.us-west-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require';

const summaryPath = 'public/engine-tests/summary.txt';
const launcherPath = 'public/engine-tests/launcher.txt';
const downloadPath = 'public/engine-tests/forge-download.log';
const rawPath = 'public/engine-tests/forge-5game.log';

const read = (p, max = 60000) => {
  try { return fs.readFileSync(p, 'utf8').slice(-max); }
  catch { return ''; }
};

const payload = [
  '=== SUMMARY ===', read(summaryPath),
  '\n=== LAUNCHER ===', read(launcherPath),
  '\n=== DOWNLOAD LOG ===', read(downloadPath, 20000),
  '\n=== RAW FORGE LOG ===', read(rawPath, 100000),
].join('\n');

try {
  const sql = neon(url);
  await sql`INSERT INTO forge_results (id, summary, updated_at)
            VALUES (1, ${payload}, now())
            ON CONFLICT (id) DO UPDATE
              SET summary = EXCLUDED.summary, updated_at = now()`;
  console.log(`Wrote ${payload.length} characters of Forge diagnostics to temporary result database.`);
} catch (err) {
  console.error('Failed to write Forge diagnostics:', err?.message || err);
}
