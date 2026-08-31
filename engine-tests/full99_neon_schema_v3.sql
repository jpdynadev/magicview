CREATE TABLE IF NOT EXISTS public.sim_game_action_traces_v3 (
  game_id text PRIMARY KEY,
  engine_id text NOT NULL,
  deck_hash text NOT NULL,
  variant text NOT NULL,
  seed bigint NOT NULL,
  seat integer NOT NULL,
  pod text NOT NULL,
  horizon integer NOT NULL,
  pilot_version text NOT NULL,
  schema_version text NOT NULL CHECK (schema_version = 'kinnan-full99-card-telemetry-v3'),
  raw_action_trace jsonb NOT NULL,
  raw_action_trace_hash text NOT NULL,
  raw_action_trace_event_count integer NOT NULL CHECK (raw_action_trace_event_count >= 0),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.sim_game_card_telemetry_v3 (
  game_id text NOT NULL REFERENCES public.sim_game_action_traces_v3(game_id) ON DELETE CASCADE,
  registered_card_id text NOT NULL,
  card_name text NOT NULL,
  deck_hash text NOT NULL,
  schema_version text NOT NULL CHECK (schema_version = 'kinnan-full99-card-telemetry-v3'),
  seen boolean NOT NULL DEFAULT false,
  opening_hand boolean NOT NULL DEFAULT false,
  kept boolean NOT NULL DEFAULT false,
  mulliganed boolean NOT NULL DEFAULT false,
  first_seen_turn integer,
  first_drawn_turn integer,
  zone_changes jsonb NOT NULL DEFAULT '[]'::jsonb,
  tutored boolean NOT NULL DEFAULT false,
  revealed boolean NOT NULL DEFAULT false,
  cast boolean NOT NULL DEFAULT false,
  played boolean NOT NULL DEFAULT false,
  mana_produced jsonb NOT NULL DEFAULT '{}'::jsonb,
  mana_spent integer NOT NULL DEFAULT 0,
  activated boolean NOT NULL DEFAULT false,
  used boolean NOT NULL DEFAULT false,
  combo_participation boolean NOT NULL DEFAULT false,
  protection_participation boolean NOT NULL DEFAULT false,
  interaction_participation boolean NOT NULL DEFAULT false,
  attempt_present boolean NOT NULL DEFAULT false,
  protected_attempt_present boolean NOT NULL DEFAULT false,
  natural_win_presence boolean NOT NULL DEFAULT false,
  package_execution boolean NOT NULL DEFAULT false,
  outcome_role text NOT NULL CHECK (outcome_role IN ('absent/notSeen','merelyPresent','involved','essential')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (game_id, registered_card_id)
);

CREATE INDEX IF NOT EXISTS sim_game_card_telemetry_v3_card_idx
  ON public.sim_game_card_telemetry_v3 (registered_card_id, deck_hash);

CREATE OR REPLACE VIEW public.sim_game_card_coverage_v3 AS
SELECT t.game_id, t.engine_id, t.deck_hash, t.variant, t.seed, t.seat, t.pod,
       count(c.*) AS actual_rows,
       count(DISTINCT c.registered_card_id) AS distinct_cards,
       bool_and(c.schema_version = 'kinnan-full99-card-telemetry-v3') AS schema_valid,
       count(c.*) = 99
         AND count(DISTINCT c.registered_card_id) = 99
         AND bool_and(c.schema_version = 'kinnan-full99-card-telemetry-v3') AS coverage_valid
FROM public.sim_game_action_traces_v3 t
LEFT JOIN public.sim_game_card_telemetry_v3 c USING (game_id)
GROUP BY t.game_id, t.engine_id, t.deck_hash, t.variant, t.seed, t.seat, t.pod;

