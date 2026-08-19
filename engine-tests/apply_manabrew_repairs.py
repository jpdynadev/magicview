#!/usr/bin/env python3
"""Apply the Kinnan lab Manabrew repairs by exact source content.

This intentionally avoids unified-diff line-number fragility.  Every upstream
block must either match exactly once or already contain the repaired block.
Any unexpected pinned-source drift is a hard failure before runtime build.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/manabrew")
HOST = ROOT / "forge-harness/src/main/java/forge/harness/host"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        print(f"already repaired: {label}")
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"repair precondition failed for {label}: expected 1 source block, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"repaired: {label}")


controller = HOST / "ManaBrewInteractiveController.java"
replace_once(
    controller,
    '''    @Override
    public String chooseCardName(final SpellAbility sa, final Predicate<ICardFace> cpp, final String valid, final String message) {
        final List<ICardFace> faces = filterCardFaces(sa, cpp, valid);
        return chooseCardName(sa, faces, message);
    }
''',
    '''    @Override
    public String chooseCardName(final SpellAbility sa, final Predicate<ICardFace> cpp, final String valid, final String message) {
        // The frozen RogSi policy casts Consultation as the second half of the
        // Oracle line. Naming a known-absent card is legal and lets Forge
        // perform the actual exile/trigger resolution without materializing
        // the entire card database as a protocol option list.
        if (sa != null && sa.getHostCard() != null
                && "Demonic Consultation".equals(sa.getHostCard().getName())) {
            return "Black Lotus";
        }
        final List<ICardFace> faces = filterCardFaces(sa, cpp, valid);
        return chooseCardName(sa, faces, message);
    }
''',
    "Demonic Consultation card-name shortcut",
)
replace_once(
    controller,
    '''        forge.StaticData.instance().getCommonCards().streamAllFaces()
                .filter(faceFilter)
                .filter(face -> {
                    if (valid == null || valid.isEmpty()) {
                        return true;
                    }
                    final PaperCard cp = forge.StaticData.instance().getCommonCards().getCard(face.getName());
''',
    '''        forge.StaticData.instance().getCommonCards().streamAllFaces()
                .filter(faceFilter)
                .filter(face -> {
                    // "Card" is ChooseCardNameEffect's unconstrained default. The
                    // face predicate already accepts it, so constructing a live Card
                    // for every printed face only consumes Forge game IDs.
                    if (valid == null || valid.isEmpty() || "Card".equals(valid)) {
                        return true;
                    }
                    final PaperCard cp = forge.StaticData.instance().getCommonCards().getCard(face.getName());
''',
    "unconstrained card-name runaway guard",
)

session = HOST / "ManaBrewInteractiveSession.java"
replace_once(
    session,
    '''    private volatile String latestPromptJson;
    private volatile int promptedPlayerIndex = -1;
    private long promptSeq;
    private volatile boolean closed;
    private volatile Thread gameThread;
    private volatile SpellAbility castingAbility;
''',
    '''    private volatile String latestPromptJson;
    private volatile int promptedPlayerIndex = -1;
    private volatile long promptSeq;
    private volatile boolean closed;
    private volatile Thread gameThread;
    private volatile SpellAbility castingAbility;
    private volatile String terminalError;
''',
    "prompt sequence visibility and terminal error state",
)
replace_once(
    session,
    '''            try {
                match.startGame(game);
            } catch (RuntimeException error) {
                System.err.println("[mana-brew] interactive game error: " + error.getMessage());
                error.printStackTrace(System.err);
            }
''',
    '''            try {
                match.startGame(game);
            } catch (RuntimeException error) {
                terminalError = error.toString();
                latestPromptJson = null;
                promptedPlayerIndex = -1;
                System.err.println("[mana-brew] interactive game error: " + error.getMessage());
                error.printStackTrace(System.err);
            }
''',
    "surface game-thread terminal errors",
)
replace_once(
    session,
    '''    public String getLatestPromptJson() {
        return latestPromptJson;
    }
''',
    '''    public String getLatestPromptJson() {
        final String prompt = latestPromptJson;
        if (prompt != null) {
            return prompt;
        }
        if (terminalError != null) {
            final JsonObject input = new JsonObject();
            input.addProperty("type", "engineError");
            input.addProperty("message", terminalError);
            final JsonObject terminal = new JsonObject();
            terminal.addProperty("promptId", "engine-error-" + sessionId);
            terminal.addProperty("decidingPlayerId", "player-0");
            terminal.add("input", input);
            return terminal.toString();
        }
        if (game != null && game.isGameOver()) {
            final JsonObject input = new JsonObject();
            input.addProperty("type", "gameOver");
            final JsonObject terminal = new JsonObject();
            terminal.addProperty("promptId", "game-over-" + sessionId);
            terminal.addProperty("decidingPlayerId", "player-0");
            terminal.add("input", input);
            return terminal.toString();
        }
        return null;
    }
''',
    "terminal prompt surfacing",
)
replace_once(
    session,
    '''    public String submitAction(final String actionJson) {
        if (closed) {
            throw new IllegalStateException("session is closed");
        }
        final JsonObject canonical = JsonParser.parseString(actionJson).getAsJsonObject();
        final JsonObject decoded = ManabrewProtocolAdapter.decodeAction(canonical);
        trace("[harness-action] recv=" + actionJson + " decoded=" + decoded);
        actions.offer(decoded);
        // No snapshot here — it would race the game thread this unblocks.
        return "";
    }
''',
    '''    public String submitAction(final String actionJson) {
        if (closed) {
            throw new IllegalStateException("session is closed");
        }
        final String visiblePrompt = latestPromptJson;
        if (visiblePrompt == null) {
            trace("[harness-action] dropped=no-current-prompt recv=" + actionJson);
            return "";
        }
        final long submittedPromptSeq = promptSeq;
        final JsonObject canonical = JsonParser.parseString(actionJson).getAsJsonObject();
        final String answeredPromptId = canonical.has("__promptId")
                && !canonical.get("__promptId").isJsonNull()
                ? canonical.get("__promptId").getAsString() : null;
        String currentPromptId = null;
        try {
            final JsonObject visible = JsonParser.parseString(visiblePrompt).getAsJsonObject();
            if (visible.has("promptId") && !visible.get("promptId").isJsonNull()) {
                currentPromptId = visible.get("promptId").getAsString();
            }
        } catch (RuntimeException ignored) {
        }
        if (answeredPromptId != null && currentPromptId != null
                && !answeredPromptId.equals(currentPromptId)) {
            trace("[harness-action] dropped=prompt-id-mismatch answered="
                    + answeredPromptId + " current=" + currentPromptId
                    + " recv=" + actionJson);
            return "";
        }
        canonical.remove("__promptId");
        final JsonObject decoded = ManabrewProtocolAdapter.decodeAction(canonical);
        decoded.addProperty("__promptSeq", submittedPromptSeq);
        trace("[harness-action] promptSeq=" + submittedPromptSeq
                + " promptId=" + currentPromptId
                + " recv=" + actionJson + " decoded=" + decoded);
        actions.offer(decoded);
        // No snapshot here — it would race the game thread this unblocks.
        return "";
    }
''',
    "prompt-scoped submitAction",
)
replace_once(
    session,
    '''            final String kind = action.has("kind") ? action.get("kind").getAsString() : "";
            if (!"concede".equals(kind)) {
                return action;
            }
            final int target = action.has("player")
                    ? action.get("player").getAsInt()
                    : promptedPlayerIndex;
            concedePlayer(target);
            if (target != promptedPlayerIndex && !gameDecided()) {
                continue;
            }
            return syntheticPass();
''',
    '''            if (action.has("__promptSeq") && !action.get("__promptSeq").isJsonNull()) {
                final long submittedPromptSeq = action.get("__promptSeq").getAsLong();
                if (submittedPromptSeq != promptSeq) {
                    trace("[harness-action] dropped=stale-prompt submitted="
                            + submittedPromptSeq + " current=" + promptSeq
                            + " action=" + action);
                    continue;
                }
            }
            final String kind = action.has("kind") ? action.get("kind").getAsString() : "";
            if (!"concede".equals(kind)) {
                latestPromptJson = null;
                promptedPlayerIndex = -1;
                return action;
            }
            final int target = action.has("player")
                    ? action.get("player").getAsInt()
                    : promptedPlayerIndex;
            concedePlayer(target);
            if (target != promptedPlayerIndex && !gameDecided()) {
                continue;
            }
            latestPromptJson = null;
            promptedPlayerIndex = -1;
            return syntheticPass();
''',
    "prompt-scoped action consumption",
)

adapter = HOST / "ManabrewProtocolAdapter.java"
replace_once(
    adapter,
    '''            final String value = map.entrySet().isEmpty() ? "" : map.entrySet().iterator().next().getKey();
''',
    '''            final String value = map.entrySet().isEmpty() ? "" : fullColorName(map.entrySet().iterator().next().getKey());
''',
    "full color-name decoding",
)
replace_once(
    adapter,
    '''    private static JsonObject parseActionId(final String actionId) {
''',
    '''    private static String fullColorName(final String token) {
        switch (token) {
            case "W": return "White";
            case "U": return "Blue";
            case "B": return "Black";
            case "R": return "Red";
            case "G": return "Green";
            case "C": return "Colorless";
            default: return token;
        }
    }

    private static JsonObject parseActionId(final String actionId) {
''',
    "color-name helper",
)

print("all Manabrew repairs applied successfully")
