CREATE TABLE IF NOT EXISTS public.sim_game_card_telemetry (
  engine_id text NOT NULL,
  deck_hash text NOT NULL,
  variant text NOT NULL,
  seed bigint NOT NULL,
  seat integer NOT NULL,
  pod text NOT NULL,
  card_identity text NOT NULL,
  schema_version text NOT NULL,
  opening_hand boolean NOT NULL DEFAULT false,
  kept boolean NOT NULL DEFAULT false,
  mulliganed boolean NOT NULL DEFAULT false,
  first_seen_turn integer,
  first_drawn_turn integer,
  zones_seen jsonb NOT NULL DEFAULT '[]'::jsonb,
  zone_changes jsonb NOT NULL DEFAULT '[]'::jsonb,
  tutored boolean NOT NULL DEFAULT false,
  revealed boolean NOT NULL DEFAULT false,
  cast boolean NOT NULL DEFAULT false,
  played boolean NOT NULL DEFAULT false,
  mana_produced integer NOT NULL DEFAULT 0,
  mana_spent integer NOT NULL DEFAULT 0,
  activated boolean NOT NULL DEFAULT false,
  used boolean NOT NULL DEFAULT false,
  combo_participation boolean NOT NULL DEFAULT false,
  protection_participation boolean NOT NULL DEFAULT false,
  interaction_participation boolean NOT NULL DEFAULT false,
  natural_win_presence boolean NOT NULL DEFAULT false,
  assembly_presence boolean NOT NULL DEFAULT false,
  attempt_presence boolean NOT NULL DEFAULT false,
  protected_attempt_presence boolean NOT NULL DEFAULT false,
  package_execution boolean NOT NULL DEFAULT false,
  outcome_attribution text NOT NULL CHECK (outcome_attribution IN ('present','involved','essential')),
  raw_action_trace jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (engine_id, deck_hash, seed, seat, pod, card_identity)
);

CREATE INDEX IF NOT EXISTS sim_game_card_telemetry_card_idx
  ON public.sim_game_card_telemetry (card_identity, deck_hash);

CREATE OR REPLACE VIEW public.sim_game_card_coverage AS
SELECT engine_id, deck_hash, variant, seed, seat, pod,
       count(*) AS actual_rows,
       count(DISTINCT card_identity) AS distinct_cards,
       bool_and(schema_version = 'kinnan-full99-card-telemetry-v2') AS schema_valid,
       count(*) = 99 AND count(DISTINCT card_identity) = 99 AS coverage_valid
FROM public.sim_game_card_telemetry
GROUP BY engine_id, deck_hash, variant, seed, seat, pod;
