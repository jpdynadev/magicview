# Kinnan lever stress-test design

Goal: identify causal levers before fine-tuning individual cards.

## Extreme archetypes

### DORK_MAX
Push creature mana density aggressively while preserving deterministic core and enough interaction/outlets. Test progressively increasing dork counts rather than one arbitrary list.

### TUTOR_MAX
Maximize compact tutor/transmute/artifact-search density while preserving mana and deterministic core. Measure whether tutor saturation improves attempts or simply creates tempo/mana bottlenecks.

### MESH_MAX
Maximize win-graph connectivity: cards should participate in multiple deterministic engines, serve as tutor nodes, outlets, or redundant bridges. Prefer multi-role cards over isolated A+B packages.

## Lever sweeps
For each axis create low/base/high/extreme settings around M25:
- mana-source density / one-mana dorks
- tutor density
- deterministic engine density
- outlet redundancy
- protection density
- card-advantage density
- land count
- average mana value / tempo cost

## Metrics
Primary: protected deterministic attempt by end of Kinnan T4.
Secondary: deterministic attempt, deterministic assembly, natural game win, opponent-win-before-Kinnan, interaction absorbed, mulligan quality, timeout/error.

Record failure reasons: mana total, colored mana, missing engine, missing outlet, tutor tempo, protection, counterwar, disruption, stax, opponent speed, mulligan, nondeterministic line, pilot/engine error.

## Search strategy
1. Extreme stress test to learn directionality.
2. Sweep each lever around the strongest region.
3. Test pairwise interactions between strongest levers (e.g. dorks x tutors, tutors x protection, engine mesh x protection).
4. Fit a simple response surface from paired-seed results.
5. Generate fine mutations only inside the high-performing region.
6. Confirm finalists against adversarial pod profiles and all four seats.

Use paired seeds for every lever comparison. Do not select on 20-game noise; screen at 100 games/configuration, then confirm promising regions at 400+ adversarial games/configuration.