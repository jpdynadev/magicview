#!/usr/bin/env bash
# One-shot Forge rules-engine diagnostic for Netlify deploy-preview workers.
# IMPORTANT: this script always exits 0 so the preview publishes logs even when Forge fails.
set +e

ROOT="$(pwd)"
OUT="$ROOT/public/engine-tests"
WORK="/tmp/kinnan-forge"
SITE_ID="${NETLIFY_SITE_ID:-71e319da-e5e4-4d65-883e-f4c2a56d19c2}"
ACCOUNT_ID="68dd77f53b061e007de461d0"
RESULT_KEY="FORGE_DIAGNOSTIC_RESULT_B64"
rm -rf "$WORK"
mkdir -p "$OUT" "$WORK/forge"

handoff_result() {
  # ChatGPT's Netlify connector can read site environment variables. Store a
  # temporary DEV-context result value through Netlify's REST API, then remove
  # it after retrieval. DEV context keeps it out of preview/production runtime.
  if [ -z "${NETLIFY_AUTH_TOKEN:-}" ]; then
    echo "NETLIFY_AUTH_TOKEN unavailable; env handoff skipped" >> "$OUT/handoff.log"
    return 0
  fi

  {
    echo "=== SUMMARY ==="
    cat "$OUT/summary.txt" 2>/dev/null || true
    echo
    echo "=== LAUNCHER ==="
    cat "$OUT/launcher.txt" 2>/dev/null || true
    echo
    echo "=== DOWNLOAD TAIL ==="
    tail -120 "$OUT/forge-download.log" 2>/dev/null || true
  } | head -c 30000 > "$OUT/handoff-payload.txt"

  RESULT_B64="$(base64 -w0 "$OUT/handoff-payload.txt" 2>/dev/null || base64 "$OUT/handoff-payload.txt" | tr -d '\n')"
  if [ -z "$RESULT_B64" ]; then
    echo "Could not encode diagnostic payload" >> "$OUT/handoff.log"
    return 0
  fi

  API_BASE="https://api.netlify.com/api/v1/accounts/$ACCOUNT_ID/env"
  AUTH_HEADER="Authorization: Bearer $NETLIFY_AUTH_TOKEN"

  # Clean stale result first. Ignore 404/no-existing-variable responses.
  curl -sS -X DELETE -H "$AUTH_HEADER" \
    "$API_BASE/$RESULT_KEY?site_id=$SITE_ID" \
    >> "$OUT/handoff.log" 2>&1 || true

  python3 - "$RESULT_B64" > "$OUT/handoff-request.json" <<'PY'
import json, sys
value = sys.argv[1]
print(json.dumps([{
    "key": "FORGE_DIAGNOSTIC_RESULT_B64",
    "scopes": ["builds"],
    "values": [{"value": value, "context": "dev"}],
    "is_secret": False,
}]))
PY

  curl -sS --fail-with-body -X POST \
    -H "$AUTH_HEADER" \
    -H 'Content-Type: application/json' \
    --data-binary @"$OUT/handoff-request.json" \
    "$API_BASE?site_id=$SITE_ID" \
    >> "$OUT/handoff.log" 2>&1
  echo "rest_handoff_status=$?" >> "$OUT/handoff.log"
}

{
  echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "pwd=$ROOT"
  echo "site_id=$SITE_ID"
  uname -a
  node --version 2>&1 || true
  npm --version 2>&1 || true
  java -version 2>&1 || true
} > "$OUT/environment.txt" 2>&1

JAVA_BIN="$(command -v java || true)"
if [ -z "$JAVA_BIN" ]; then
  echo "System Java missing; downloading Temurin JRE 17" >> "$OUT/environment.txt"
  curl -L --fail --retry 3 --connect-timeout 20 \
    -o "$WORK/jre17.tar.gz" \
    'https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jre/hotspot/normal/eclipse' \
    >> "$OUT/java-download.log" 2>&1
  if [ -s "$WORK/jre17.tar.gz" ]; then
    mkdir -p "$WORK/jre"
    tar -xzf "$WORK/jre17.tar.gz" -C "$WORK/jre" --strip-components=1 >> "$OUT/java-download.log" 2>&1
    JAVA_BIN="$WORK/jre/bin/java"
  fi
fi

if [ -z "$JAVA_BIN" ] || [ ! -x "$JAVA_BIN" ]; then
  echo "ERROR: no Java runtime available" > "$OUT/forge-5game.log"
  cp "$OUT/forge-5game.log" "$OUT/summary.txt"
  handoff_result
  exit 0
fi

FORGE_URL='https://github.com/Card-Forge/forge/releases/download/forge-2.0.13/forge-installer-2.0.13.tar.bz2'
echo "Downloading $FORGE_URL" > "$OUT/forge-download.log"
curl -L --fail --retry 3 --retry-all-errors --connect-timeout 30 \
  -o "$WORK/forge.tar.bz2" "$FORGE_URL" >> "$OUT/forge-download.log" 2>&1
CURL_STATUS=$?
echo "curl_status=$CURL_STATUS" >> "$OUT/forge-download.log"
ls -lh "$WORK/forge.tar.bz2" >> "$OUT/forge-download.log" 2>&1 || true

if [ $CURL_STATUS -ne 0 ] || [ ! -s "$WORK/forge.tar.bz2" ]; then
  echo "ERROR: Forge archive download failed" > "$OUT/forge-5game.log"
  cat "$OUT/forge-download.log" >> "$OUT/forge-5game.log"
  cp "$OUT/forge-5game.log" "$OUT/summary.txt"
  handoff_result
  exit 0
fi

tar -xjf "$WORK/forge.tar.bz2" -C "$WORK/forge" >> "$OUT/forge-download.log" 2>&1
TAR_STATUS=$?
echo "tar_status=$TAR_STATUS" >> "$OUT/forge-download.log"
find "$WORK/forge" -maxdepth 5 -type f | sort > "$OUT/forge-tree.txt" 2>&1

if [ $TAR_STATUS -ne 0 ]; then
  echo "ERROR: Forge archive extraction failed" > "$OUT/forge-5game.log"
  tail -200 "$OUT/forge-download.log" >> "$OUT/forge-5game.log"
  cp "$OUT/forge-5game.log" "$OUT/summary.txt"
  handoff_result
  exit 0
fi

# Prefer an actual desktop Forge jar; avoid installer/helper jars when possible.
JAR="$(find "$WORK/forge" -type f -name 'forge*.jar' 2>/dev/null | grep -Ev 'installer|android|updater|skin' | head -n 1)"
if [ -z "$JAR" ]; then
  JAR="$(find "$WORK/forge" -type f -name '*.jar' 2>/dev/null | grep -Ev 'installer|android|updater|skin' | head -n 1)"
fi
FORGE_SH="$(find "$WORK/forge" -type f -name 'forge.sh' 2>/dev/null | head -n 1)"

{
  echo "JAVA_BIN=$JAVA_BIN"
  echo "JAR=$JAR"
  echo "FORGE_SH=$FORGE_SH"
} > "$OUT/launcher.txt"

run_sim() {
  if [ -n "$JAR" ] && [ -f "$JAR" ]; then
    JARDIR="$(dirname "$JAR")"
    echo "Launching jar from $JARDIR" >> "$OUT/launcher.txt"
    (
      cd "$JARDIR" || exit 97
      "$JAVA_BIN" -Xmx3g -jar "$JAR" sim \
        -D "$ROOT/engine-tests/decks" \
        -d Kinnan_TestB.dck RogSi_2026.dck Blue_Farm_2026.dck RogThras_2026.dck \
        -f commander -n 5 -c 120
    ) > "$OUT/forge-5game.log" 2>&1
    return $?
  elif [ -n "$FORGE_SH" ] && [ -f "$FORGE_SH" ]; then
    SHDIR="$(dirname "$FORGE_SH")"
    echo "Launching forge.sh from $SHDIR" >> "$OUT/launcher.txt"
    (
      cd "$SHDIR" || exit 97
      bash "./$(basename "$FORGE_SH")" sim \
        -D "$ROOT/engine-tests/decks" \
        -d Kinnan_TestB.dck RogSi_2026.dck Blue_Farm_2026.dck RogThras_2026.dck \
        -f commander -n 5 -c 120
    ) > "$OUT/forge-5game.log" 2>&1
    return $?
  else
    echo "ERROR: no runnable Forge jar or forge.sh found" > "$OUT/forge-5game.log"
    return 98
  fi
}

run_sim
SIM_STATUS=$?
echo "sim_status=$SIM_STATUS" >> "$OUT/launcher.txt"

{
  echo "=== FORGE DIAGNOSTIC SUMMARY ==="
  echo "sim_status=$SIM_STATUS"
  echo
  echo "=== Winner-like lines ==="
  grep -Ei 'winner| wins|victory|match result|game over' "$OUT/forge-5game.log" || true
  echo
  echo "=== Error / unsupported / deck lines ==="
  grep -Ei 'error|exception|unsupported|unknown card|not found|invalid|deck' "$OUT/forge-5game.log" | tail -250 || true
  echo
  echo "=== Kinnan / combo mentions ==="
  grep -Ei 'Kinnan|Basalt Monolith|Power Artifact|Freed from the Real|Pemmin|Thrasios' "$OUT/forge-5game.log" | tail -250 || true
  echo
  echo "=== Last 120 raw log lines ==="
  tail -120 "$OUT/forge-5game.log" || true
} > "$OUT/summary.txt" 2>&1

handoff_result

# Never fail the Netlify preview build; the whole point is to publish diagnostics.
exit 0
