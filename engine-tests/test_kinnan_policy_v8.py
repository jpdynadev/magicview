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


if __name__ == "__main__":
    unittest.main()
