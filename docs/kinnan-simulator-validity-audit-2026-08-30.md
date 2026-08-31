# Kinnan Simulator Validity Audit

Audience: Kinnan V2 Lab maintainers
Date: 2026-08-30

## Executive answer

The evidence does not support the broad claim that F10 is the best Kinnan 99. F10 is only the incumbent under the current v8 pilot and the protected-attempt-by-T4 surrogate. The pilot contains explicit card-name and combo-line preferences that align with F10's artifact-tutor/Monolith architecture, while materially different tournament-winning Kinnan architectures are not recognized by the deterministic-line or attempt logic. Until policy parity, endpoint validation, and untouched holdout confirmation are established, deck rankings are frozen.

## Consequential findings

1. Differential pilot support is real, not hypothetical. `manabrew_pilot_v8.py` gives bespoke keep, cast, tutor-target, and combo-execution scores to Basalt Monolith, Grim Monolith, Power Artifact, artifact tutors, Thrasios, Staff, Ballista, and related F10 lines. Generic or new cards fall back to substantially less-informed scoring.
2. `kinnan_policy_v8.py` recognizes only a narrow set of Monolith, Power Artifact, Forensic Gadgeteer, and Machine God's Effigy states as deterministic. Attempt recognition is restricted to named outlets/activations. This makes unrecognized decks unable to score the primary endpoint even when Forge can legally execute their cards.
3. `protectedAttempt` is a card-presence proxy: it becomes true when a named protection card is present in hand/battlefield at the first recognized attempt. It does not require actual hostile interaction, correct sequencing, stack resolution, or a realized win.
4. Natural wins are too rare to validate the surrogate. The incumbent bank reports roughly 0.3% natural wins versus 3.5–3.8% protected attempts. Most ranking weight therefore comes from an unvalidated proxy.
5. The repeated canonical 200-key bank has been used adaptively to select follow-up packages and exposure hypotheses. This risks test-set overfitting and invalidates naive repeated p-value interpretation.
6. Failure to find a statistically significant challenger is not evidence that F10 is best. Most reported comparisons are low-power screens with large uncertainty; promotion requires effect intervals, a predeclared margin, and untouched confirmation.
7. Recent protocol defects (Monolith affordability, JVM lifecycle, wrong v1.51 swap, land-as-cast, false draws, and missing payment attribution) show that green workflow status alone is not sufficient evidence of model validity.

## External anchors

- Sterling Sellards won the 80-player TopDeck Invitational on 2026-08-22 with a 52-creature Kinnan list that contains no Basalt Monolith, Grim Monolith, Power Artifact, Thrasios, Staff of Domination, Walking Ballista, or Machine God's Effigy. Under the present line recognizer, its core architecture cannot earn the same deterministic endpoint as F10.
- Jonathon Foster won a 128-player event on 2026-06-27 with a 50-creature Kinnan architecture centered on creature mana, copy effects, Seedborn-style engines, Freed from the Real, and large Kinnan hits.
- Janos Nado won a 308-player event on 2026-06-13 with a conventional 25-creature artifact/tutor/control shell. These three successful lists establish that the relevant architecture space is much broader than local F10 mutations.

## Required ranking-validity gate

No deck may be called best or promoted until all of the following pass:

1. Full-99 telemetry: exactly 99 rows per valid game, semantic payment/source attribution, raw trace retention, and complete schema validation.
2. Policy parity: every changed card and every declared win line has executable tests for casting, modes, costs, targets, tutoring, activation, and combo sequencing. Unsupported cards make the comparison NR.
3. Symmetry tests: equivalent game states and effect-equivalent cards must produce equivalent decisions; card-name renaming should not materially change policy behavior.
4. Line-complete golden scenarios: include Monolith, Power Artifact, creature-tap/copy, Pili-Pala/Knacksaw, Freed from the Real, Seedborn/value, and recovery-after-disruption families represented by current tournament lists.
5. Endpoint suite: retain protected T4 attempt as a diagnostic, but add actual wins through T6/T8, resolved attempts under stack interaction, post-disruption recovery, and time-to-win. Validate the surrogate against realized outcomes before using it as the primary ranker.
6. Metagame validity: test multiple current opponent archetypes and calibrated opponent policies, with randomized pod composition and all seats.
7. Statistical separation: use a development bank for mutation generation and a sealed, untouched confirmation bank; preregister the candidate, endpoint, and practical margin; report paired confidence intervals and multiplicity-aware evidence.
8. External-anchor sanity test: run at least three exact recent tournament-winning Kinnan 99s with deck-specific semantics complete. Their purpose is model falsification and calibration, not automatic promotion.

## Current operational state

- Full-99 telemetry validation run 33330866873 passed on four games: 396 expected rows, 396 actual rows, zero missing cards, zero duplicates, schema `kinnan-full99-card-telemetry-v2`, `semanticValid: true`, and `telemetryComplete: true`.
- This four-game pass validates instrumentation only. It does not validate the pilot, surrogate endpoint, opponent model, or ranking.
- The community queue has no runnable queued Kinnan submission. Submission C0FE096A17 is correctly held as `needs_pilot` because its exact 99 uses Seedborn/Leech Bonder infrastructure the current pilot does not model.
- Legacy v1.29/v1.30 screens remain NR because they lack mandatory full-99 telemetry and policy parity.
- No serious optimization compute should start until the policy-parity and endpoint gates above are implemented.

## Sources

- Repository pilot: https://github.com/jpdynadev/magicview/blob/agent/kinnan-v152-full99-telemetry-repair/engine-tests/manabrew_pilot_v8.py
- Repository policy: https://github.com/jpdynadev/magicview/blob/agent/kinnan-v152-full99-telemetry-repair/engine-tests/kinnan_policy_v8.py
- Base card-name scoring: https://github.com/jpdynadev/magicview/blob/agent/kinnan-v152-full99-telemetry-repair/engine-tests/manabrew_pilot.py
- Telemetry validation: https://github.com/jpdynadev/magicview/actions/runs/33330866873
- Sterling Sellards deck: https://topdeck.gg/deck/topdeck-invitational-2026/vIFmUxrSS9MXudrGipbCepvdYnl1
- Jonathon Foster deck: https://topdeck.gg/deck/instock-presents-rumble-in-the-dungeon-con/HrXt81PI3oPKl21P5PdykepklSB2
- Janos Nado deck: https://topdeck.gg/deck/level-7s-siege-at-the-castle-10k/10XZGpOw5vVlD7VeYRO1XvBv3Ft2
- EDHTop16 current Kinnan results: https://edhtop16.com/commander/Kinnan,%20Bonder%20Prodigy?sortBy=TOP&timePeriod=THREE_MONTHS
- Dwork et al., reusable holdout: https://pubmed.ncbi.nlm.nih.gov/26250683/
- ASA p-value statement: https://www.tandfonline.com/doi/full/10.1080/00031305.2016.1154108
- Sargent, simulation verification and validation: https://surface.syr.edu/eecs/7/
- FDA surrogate endpoint validation principles: https://www.fda.gov/drugs/development-resources/surrogate-endpoint-resources-drug-and-biologic-development
- 17Lands public datasets: https://www.17lands.com/public_datasets

