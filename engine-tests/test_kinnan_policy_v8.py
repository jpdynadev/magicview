import unittest

import kinnan_policy_v8 as policy


def card(card_id, name, controller="player-0", power="1", toughness="1"):
    return {
        "id": card_id,
        "identity": {"name": name},
        "controllerId": controller,
        "ownerId": controller,
        "power": power,
        "toughness": toughness,
        "types": ["Creature"],
    }


class PolicyTests(unittest.TestCase):
    def test_authoritative_winner_comes_from_snapshot(self):
        self.assertEqual(policy.authoritative_winner({"gameOver": True, "winnerId": "player-2"}), 2)
        self.assertIsNone(policy.authoritative_winner({"gameOver": True, "winnerId": None}))

    def test_dynamic_kinnan_seat_combo_detection(self):
        snapshot = {
            "zones": [
                {
                    "ownerId": "player-2",
                    "zone": "battlefield",
                    "cards": [card("k", "Kinnan, Bonder Prodigy", "player-2"), card("b", "Basalt Monolith", "player-2")],
                },
                {
                    "ownerId": "player-2",
                    "zone": "hand",
                    "cards": [card("w", "Walking Ballista", "player-2")],
                },
            ]
        }
        self.assertIn("Kinnan + Basalt", policy.deterministic_line(snapshot, 2))
        self.assertIsNone(policy.deterministic_line(snapshot, 0))

    def test_kinnan_basalt_is_deterministic_via_exhaustive_activations(self):
        snapshot = {
            "zones": [
                {
                    "ownerId": "player-0",
                    "zone": "battlefield",
                    "cards": [card("k", "Kinnan, Bonder Prodigy"), card("b", "Basalt Monolith")],
                }
            ]
        }
        self.assertIn("exhaustive Kinnan activations", policy.deterministic_line(snapshot, 0))

    def test_attackers_are_legal_and_kinnan_engines_stay_home(self):
        snapshot = {
            "players": [
                {"id": "player-0", "life": 40},
                {"id": "player-1", "life": 9},
                {"id": "player-2", "life": 20},
            ],
            "zones": [
                {
                    "ownerId": "player-0",
                    "zone": "battlefield",
                    "cards": [card("k", "Kinnan, Bonder Prodigy"), card("e", "Elvish Mystic")],
                }
            ],
        }
        inp = {
            "attackers": [
                {"attackerId": "k", "validTargetIds": ["player-1", "player-2"]},
                {"attackerId": "e", "validTargetIds": ["player-1", "player-2"]},
            ]
        }
        self.assertEqual(
            policy.choose_attackers(inp, snapshot, 0, "Kinnan"),
            [{"attackerId": "e", "targetId": "player-1"}],
        )

    def test_selection_respects_weight_budget(self):
        inp = {
            "minTotal": 2,
            "maxTotal": 2,
            "options": [
                {"label": "Draw two cards", "weight": 2, "canRepeat": False},
                {"label": "Discard a card", "weight": 1, "canRepeat": True},
            ],
        }
        self.assertEqual(policy.choose_selection(inp, "Kinnan"), [0])

    def test_boolean_does_not_auto_accept_optional_costs(self):
        inp = {
            "presentation": {"title": "Buyback", "description": "Pay buyback?"},
            "confirmLabel": "Pay",
        }
        self.assertFalse(policy.choose_boolean(inp, "Kinnan", combo_ready=False))
        self.assertTrue(policy.choose_boolean(inp, "Kinnan", combo_ready=True))

    def test_boolean_accepts_required_life_payment(self):
        inp = {"presentation": {"title": "Pay 1 life", "targets": []}}
        self.assertTrue(policy.choose_boolean(inp, "Kinnan", combo_ready=False))

    def test_boolean_accepts_fetchland_sacrifice(self):
        inp = {"presentation": {"title": "Sacrifice Flooded Strand", "targets": []}}
        self.assertTrue(policy.choose_boolean(inp, "Kinnan", combo_ready=False))

    def test_blockers_respect_minimum_blocker_count(self):
        snapshot = {
            "players": [{"id": "player-0", "life": 40}],
            "zones": [
                {
                    "ownerId": "player-0",
                    "zone": "battlefield",
                    "cards": [card("b", "Rograkh, Son of Rohgahh", power="0", toughness="1")],
                }
            ],
        }
        inp = {
            "availableBlockerIds": ["b"],
            "attackers": [
                {
                    "attackerId": "a",
                    "validBlockerIds": ["b"],
                    "minBlockers": 2,
                    "mustBeBlocked": False,
                }
            ],
        }
        self.assertEqual(policy.choose_blockers(inp, snapshot, 0, "RogSi"), [])

    def test_payment_prefers_required_color(self):
        inp = {
            "manaCost": "{B}",
            "canConfirmFromPool": False,
            "actions": [
                {
                    "id": "tap:land:W",
                    "type": "activateManaAbility",
                    "producedMana": [{"color": "W", "amount": 1}],
                },
                {
                    "id": "tap:land:B",
                    "type": "activateManaAbility",
                    "producedMana": [{"color": "B", "amount": 1}],
                },
            ],
        }
        self.assertEqual(policy.choose_payment_action(inp), ("act", "tap:land:B"))

    def test_payment_confirms_satisfied_pool(self):
        self.assertEqual(policy.choose_payment_action({"canConfirmFromPool": True}), ("confirm", None))

    def test_payment_rejects_net_negative_filter(self):
        inp = {
            "manaCost": "{2}{U}",
            "canConfirmFromPool": False,
            "actions": [
                {
                    "id": "tap:refractor:U",
                    "type": "activateManaAbility",
                    "cost": "{2}",
                    "producedMana": [{"color": "U", "amount": 1}],
                }
            ],
        }
        self.assertEqual(policy.choose_payment_action(inp), ("cancel", None))

    def test_payment_rejects_unannotated_convoke_or_filter_action(self):
        inp = {
            "manaCost": "{G}{G}",
            "canConfirmFromPool": False,
            "actions": [
                {
                    "id": "tap:creature",
                    "type": "activateManaAbility",
                    "description": "Rograkh, Son of Rohgahh",
                },
                {
                    "id": "tap:refractor",
                    "type": "activateManaAbility",
                    "description": "Energy Refractor",
                },
            ],
        }
        self.assertEqual(policy.choose_payment_action(inp), ("cancel", None))

    def test_payment_accepts_command_tower_without_produced_mana_metadata(self):
        inp = {
            "manaCost": "{2}{U}",
            "canConfirmFromPool": False,
            "actions": [
                {
                    "id": "tap:tower:0",
                    "type": "activateManaAbility",
                    "description": "Command Tower",
                    "isManaAbility": True,
                    "cost": "{T}",
                }
            ],
        }
        self.assertEqual(policy.choose_payment_action(inp), ("act", "tap:tower:0"))

    def test_payment_color_follows_remaining_colored_cost(self):
        inp = {"availableColors": ["W", "U", "B", "R", "G"]}
        self.assertEqual(policy.choose_payment_color(inp, ["G", "U"]), "G")

    def test_repeated_main_phase_pass_targets_begin_combat(self):
        snapshot = {
            "activePlayerId": "player-1",
            "step": "main1",
            "stack": [],
            "players": [{"id": f"player-{index}"} for index in range(4)],
        }
        self.assertEqual(
            policy.recovered_pass_output(snapshot),
            {
                "type": "pass",
                "exhaustStack": False,
                "until": {"playerId": "player-1", "phase": "combatBegin"},
            },
        )

    def test_stack_pass_uses_documented_exhaust_mode(self):
        snapshot = {"activePlayerId": "player-1", "step": "main1", "stack": [{"id": 7}]}
        self.assertEqual(
            policy.recovered_pass_output(snapshot),
            {"type": "pass", "exhaustStack": True},
        )

    def test_combo_executor_prefers_basalt_untap_to_unrelated_cast(self):
        line = "Kinnan + Basalt -> exhaustive Kinnan activations -> Thrasios -> Ballista"
        untap = {"type": "activateAbility", "description": "{3}: Untap this artifact."}
        trophy = {"type": "cast", "label": "Cast Trophy Mage"}
        self.assertGreater(
            policy.combo_action_score(line, "Basalt Monolith", untap),
            policy.combo_action_score(line, "Trophy Mage", trophy),
        )

    def test_attempt_requires_outlet_or_engine_activation(self):
        line = "Kinnan + Basalt -> exhaustive Kinnan activations -> Thrasios -> Ballista"
        self.assertFalse(
            policy.is_attempt_action(line, "Basalt Monolith", {"type": "activateAbility"})
        )
        self.assertFalse(policy.is_attempt_action(line, "Trophy Mage", {"type": "cast"}))
        self.assertTrue(
            policy.is_attempt_action(
                line, "Kinnan, Bonder Prodigy", {"type": "activateAbility"}
            )
        )

    def test_basalt_power_needs_an_outlet_for_deterministic_label(self):
        snapshot = {
            "zones": [
                {
                    "ownerId": "player-0",
                    "zone": "battlefield",
                    "cards": [
                        card("b", "Basalt Monolith"),
                        card("p", "Power Artifact"),
                    ],
                }
            ]
        }
        self.assertIsNone(policy.deterministic_line(snapshot, 0))
        snapshot["zones"].append(
            {
                "ownerId": "player-0",
                "zone": "hand",
                "cards": [card("w", "Walking Ballista")],
            }
        )
        self.assertIn("Basalt Monolith + Power Artifact", policy.deterministic_line(snapshot, 0))


if __name__ == "__main__":
    unittest.main()
