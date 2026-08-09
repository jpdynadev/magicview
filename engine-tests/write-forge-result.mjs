import fs from 'node:fs';
import pg from 'pg';

const url = process.env.FORGE_RESULT_DATABASE_URL;
if (!url) {
  console.error('FORGE_RESULT_DATABASE_URL is missing');
  process.exit(0);
}

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

const client = new pg.Client({ connectionString: url });
try {
  await client.connect();
  await client.query(
    `INSERT INTO forge_results (id, summary, updated_at)
     VALUES (1, $1, now())
     ON CONFLICT (id) DO UPDATE
       SET summary = EXCLUDED.summary, updated_at = now()`,
    [payload],
  );
  console.log(`Wrote ${payload.length} characters of Forge diagnostics to temporary result database.`);
} catch (err) {
  console.error('Failed to write Forge diagnostics:', err?.message || err);
} finally {
  try { await client.end(); } catch {}
}
