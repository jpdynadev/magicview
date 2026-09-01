#!/usr/bin/env python3
from __future__ import annotations
import unittest
from pathlib import Path

from kinnan_semantics_v9 import *
from kinnan_v9_forge_canary import (
    _chosen_cost_confirmation,
    _chosen_optional_entry_payment,
    _kinnan_horizon_reached,
    _material_snapshot,
    _pay_mana_cost_answer,
    _semantic_prompt_trace,
    _stable_hash,
)


class ManaTests(unittest.TestCase):
    def test_parse_cost(self): self.assertEqual(ManaVector.parse_cost("{2}{G}{U}"), ManaVector(generic=2,G=1,U=1))
    def test_reject_ambiguous_cost(self):
        with self.assertRaises(SemanticError): ManaVector.parse_cost("{X}{G}")
    def test_exact_mana_and_convoke_are_distinct(self):
        l=ManaLedger(); l.record_production(ManaProductionEvent("tap","bird","mana",ManaVector(G=1))); l.record_payment(PaymentComponent("pay","bird",ManaVector(G=1),PaymentKind.MANA,"chord")); l.record_payment(PaymentComponent("conv","elf",ManaVector(generic=1),PaymentKind.CONVOKE,"chord"))
        self.assertEqual(l.mana_produced(),ManaVector(G=1)); self.assertEqual(l.mana_spent(),ManaVector(G=1)); self.assertEqual(l.nonmana_payment_units("chord"),1); self.assertTrue(l.validate_consumer("chord",ManaVector(generic=1,G=1))["valid"])
    def test_convoke_never_counts_as_mana_production(self):
        l=ManaLedger(); l.record_payment(PaymentComponent("conv","c",ManaVector(generic=2),PaymentKind.CONVOKE,"spell")); self.assertEqual(l.mana_produced().total(),0)
    def test_payment_deficit_fails_closed(self):
        l=ManaLedger(); l.record_payment(PaymentComponent("blue","island",ManaVector(U=1),PaymentKind.MANA,"spell")); r=l.validate_consumer("spell",ManaVector(generic=2,U=1)); self.assertFalse(r["valid"]); self.assertEqual(r["deficits"]["generic"],2)


class SelectionTests(unittest.TestCase):
    def test_copy_choice_is_not_target(self):
        c=CopyChoice("clone","seedborn",True); self.assertIsNone(c.target_object_id)
        with self.assertRaises(SemanticError): CopyChoice("clone","seedborn",True,"seedborn")
    def test_search_constraint(self):
        c=SelectionConstraint(SelectionKind.SEARCH,required_types=frozenset({"creature"}),exact_mana_value=3); self.assertTrue(c.validate([{"id":"x","types":["Creature"],"manaValue":3}])); self.assertFalse(c.validate([{"id":"x","types":["Artifact"],"manaValue":3}]))
    def test_vannifar_exact_plus_one(self):
        lib=[{"id":"c2","types":["Creature"],"manaValue":2},{"id":"c3","types":["Creature"],"manaValue":3},{"id":"a3","types":["Artifact"],"manaValue":3},{"id":"c4","types":["Creature"],"manaValue":4}]; self.assertEqual([c["id"] for c in vannifar_candidates(2,lib)],["c3"])


class ExilePermissionTests(unittest.TestCase):
    def test_knacksaw_permission_requires_identity_window_and_engine_action(self):
        ledger=ExilePermissionLedger(); ledger.grant(ExilePlayPermission("perm","clique","exiled","player-0",4,4))
        self.assertEqual(ledger.legal_permissions(card_id="exiled",player_id="player-0",turn=4,kind=ExilePlayKind.CAST,engine_action_id="cast-1"),["perm"])
        self.assertEqual(ledger.legal_permissions(card_id="exiled",player_id="player-0",turn=5,kind=ExilePlayKind.CAST,engine_action_id="cast-1"),[])
        self.assertEqual(ledger.legal_permissions(card_id="exiled",player_id="player-0",turn=4,kind=ExilePlayKind.CAST,engine_action_id=None),[])
    def test_knacksaw_permission_does_not_apply_to_other_card_or_player(self):
        ledger=ExilePermissionLedger(); ledger.grant(ExilePlayPermission("perm","clique","exiled","player-0",4,4))
        self.assertEqual(ledger.legal_permissions(card_id="other",player_id="player-0",turn=4,kind=ExilePlayKind.CAST,engine_action_id="x"),[])
        self.assertEqual(ledger.legal_permissions(card_id="exiled",player_id="player-1",turn=4,kind=ExilePlayKind.CAST,engine_action_id="x"),[])


class SoulbondPriorityTests(unittest.TestCase):
    def test_blink_breaks_soulbond_and_requires_new_object(self):
        s=SoulbondState(); s.pair("deadeye1","drake1"); s.blink("drake1","drake2"); self.assertIsNone(s.partner("deadeye1")); self.assertIsNone(s.partner("drake1"));
        with self.assertRaises(SemanticError): s.blink("deadeye1","deadeye1")
    def test_no_priority_during_untap(self):
        self.assertFalse(priority_available(phase="beginning",step="untap",engine_priority_holder="p0")); self.assertTrue(priority_available(phase="ending",step="end",engine_priority_holder="p0")); self.assertFalse(priority_available(phase="ending",step="end",engine_priority_holder=None))


class ProtectionTests(unittest.TestCase):
    def test_card_availability_alone_does_not_protect(self):
        s=ProtectionCausality().protected_line("line"); self.assertFalse(s["interactionAttempted"]); self.assertFalse(s["reactivelyProtected"]); self.assertFalse(s["attemptSurvivedInteraction"])
    def test_resolved_response_must_neutralize_explicit_threat(self):
        p=ProtectionCausality(); p.push(StackObject("threat","opp","force","counter",threatens_line_id="line")); p.push(StackObject("protect","k","swan","counter"),response_to="threat"); self.assertFalse(p.protected_line("line")["reactivelyProtected"]); p.resolve(ResolutionEvent("protect","resolved")); p.resolve(ResolutionEvent("threat","countered","protect")); s=p.protected_line("line"); self.assertTrue(s["reactivelyProtected"]); self.assertTrue(s["attemptSurvivedInteraction"])
    def test_failed_protection_does_not_count(self):
        p=ProtectionCausality(); p.push(StackObject("threat","opp","removal","remove",threatens_line_id="line")); p.push(StackObject("protect","k","counter","counter"),response_to="threat"); p.resolve(ResolutionEvent("protect","countered")); p.resolve(ResolutionEvent("threat","resolved")); s=p.protected_line("line"); self.assertFalse(s["reactivelyProtected"]); self.assertFalse(s["attemptSurvivedInteraction"])


class ComboTests(unittest.TestCase):
    def test_positive_repeatable_resource_cycle(self):
        ts=[ResourceTransform("tap",ResourceDelta(tapped_ready_resources=1),ResourceDelta(mana=3),frozenset({"mana_engine"})),ResourceTransform("untap",ResourceDelta(mana=2),ResourceDelta(tapped_ready_resources=1),frozenset({"untap_engine"}))]; w=prove_repeatable_cycle("loop",ts,available_roles={"mana_engine","untap_engine","outlet"},outlet_role="outlet"); self.assertIsNotNone(w); self.assertEqual(w.net_per_cycle.mana,1)
    def test_nonproductive_or_missing_role_cycle_rejected(self):
        ts=[ResourceTransform("tap",ResourceDelta(tapped_ready_resources=1),ResourceDelta(mana=2),frozenset({"mana_engine"})),ResourceTransform("untap",ResourceDelta(mana=2),ResourceDelta(tapped_ready_resources=1),frozenset({"untap_engine"}))]; self.assertIsNone(prove_repeatable_cycle("neutral",ts,available_roles={"mana_engine","untap_engine"})); self.assertIsNone(prove_repeatable_cycle("missing",ts,available_roles={"mana_engine","outlet"},outlet_role="outlet"))


class RoleSymmetryTests(unittest.TestCase):
    def test_same_typed_semantics_same_score_despite_card_name(self):
        a={"name":"Known","types":["Creature"],"manaValue":2,"abilities":[{"kind":"search"}],"semanticTags":["protection"]}; b={**a,"name":"New"}; pa=SemanticRoleProfile.from_typed_metadata(a); pb=SemanticRoleProfile.from_typed_metadata(b); self.assertEqual(pa,pb); self.assertEqual(architecture_neutral_role_score(pa),architecture_neutral_role_score(pb))


class Full99Tests(unittest.TestCase):
    @staticmethod
    def cards(): return [{"registeredCardId":f"c{i}","cardName":f"Card {i}"} for i in range(99)]
    def test_explicit_rows_for_all_99_including_unseen(self):
        rows=build_full99_rows(game_id="g1",deck_hash="d",registered_cards=self.cards(),observed_by_card_id={"c7":{"seen":True,"cast":True,"involved":True,"attemptPresent":True}}); self.assertEqual(len(rows),99); u=next(r for r in rows if r["registeredCardId"]=="c8"); self.assertFalse(u["seen"]); self.assertFalse(u["cast"]); self.assertEqual(u["outcomeRole"],OutcomeRole.ABSENT_NOT_SEEN.value); self.assertEqual(next(r for r in rows if r["registeredCardId"]=="c7")["outcomeRole"],OutcomeRole.INVOLVED.value)
    def test_coverage_is_exact_valid_games_times_99(self):
        rows=[]; reg={}
        for gid in ("g1","g2","g3","g4"):
            cards=self.cards(); reg[gid]=[c["registeredCardId"] for c in cards]; rows += build_full99_rows(game_id=gid,deck_hash="d",registered_cards=cards,observed_by_card_id={})
        r=validate_full99_coverage(rows,valid_game_ids=list(reg),registered_card_ids_by_game=reg); self.assertTrue(r["valid"],r); self.assertEqual(r["expectedRows"],396); self.assertEqual(r["actualRows"],396)
    def test_missing_duplicate_unknown_fail(self):
        cards=self.cards(); reg={"g":[c["registeredCardId"] for c in cards]}; rows=build_full99_rows(game_id="g",deck_hash="d",registered_cards=cards,observed_by_card_id={}); bad=rows[:-1]+[dict(rows[0])]; r=validate_full99_coverage(bad,valid_game_ids=["g"],registered_card_ids_by_game=reg); self.assertFalse(r["valid"]); self.assertIn("g",r["missingCards"]); self.assertIn("g",r["duplicates"])
    def test_unknown_observation_rejected(self):
        with self.assertRaises(SemanticError): build_full99_rows(game_id="g",deck_hash="d",registered_cards=self.cards(),observed_by_card_id={"not-registered":{"seen":True}})


class PolicyFamilyTests(unittest.TestCase):
    def test_pili_family_positive(self):
        import kinnan_policy_v9 as p; w=p.prove_pili_family(produced_mana=3,untap_cost=2,available_roles={"pili_mana_engine","pili_untap_engine","outlet"},outlet_role="outlet",essential_card_ids=["pili","grant"]); self.assertIsNotNone(w); self.assertEqual(w.net_per_cycle.mana,1)
    def test_pili_family_negative(self):
        import kinnan_policy_v9 as p; self.assertIsNone(p.prove_pili_family(produced_mana=2,untap_cost=2,available_roles={"pili_mana_engine","pili_untap_engine"},outlet_role=None,essential_card_ids=["pili","grant"]))
    def test_freed_family_positive(self):
        import kinnan_policy_v9 as p; self.assertIsNotNone(p.prove_freed_family(source_mana=3,untap_cost=1,available_roles={"enchanted_mana_source","aura_untapper","outlet"},outlet_role="outlet",essential_card_ids=["source","aura"]))
    def test_freed_family_negative(self):
        import kinnan_policy_v9 as p; self.assertIsNone(p.prove_freed_family(source_mana=1,untap_cost=2,available_roles={"enchanted_mana_source","aura_untapper","outlet"},outlet_role="outlet",essential_card_ids=["source","aura"]))
    def test_monolith_family_positive(self):
        import kinnan_policy_v9 as p; self.assertIsNotNone(p.prove_monolith_family(produced_mana=3,untap_cost=2,available_roles={"monolith_mana_engine","monolith_untap_engine","outlet"},outlet_role="outlet",essential_card_ids=["m","r"]))
    def test_monolith_family_negative(self):
        import kinnan_policy_v9 as p; self.assertIsNone(p.prove_monolith_family(produced_mana=3,untap_cost=4,available_roles={"monolith_mana_engine","monolith_untap_engine","outlet"},outlet_role="outlet",essential_card_ids=["m"]))
    def test_deadeye_family_positive(self):
        import kinnan_policy_v9 as p; self.assertIsNotNone(p.prove_deadeye_family(etb_mana_gain=5,blink_cost=2,available_roles={"soulbond_blink_engine","etb_resource_engine","outlet"},outlet_role="outlet",essential_card_ids=["deadeye","etb"]))
    def test_deadeye_family_negative(self):
        import kinnan_policy_v9 as p; self.assertIsNone(p.prove_deadeye_family(etb_mana_gain=1,blink_cost=2,available_roles={"soulbond_blink_engine","etb_resource_engine","outlet"},outlet_role="outlet",essential_card_ids=["deadeye","etb"]))
    def test_knacksaw_family_positive_library_exile_cycle(self):
        import kinnan_policy_v9 as p; w=p.prove_knacksaw_family(produced_mana=2,untap_cost=2,cards_exiled_per_cycle=1,available_roles={"knacksaw_mana_engine","knacksaw_untap_engine","library_exile_outlet"},essential_card_ids=["clique","grant"]); self.assertIsNotNone(w); self.assertEqual(w.net_per_cycle.opponent_library_exiled,1)
    def test_knacksaw_family_rejects_nonexiling_or_resource_negative_cycle(self):
        import kinnan_policy_v9 as p; self.assertIsNone(p.prove_knacksaw_family(produced_mana=2,untap_cost=2,cards_exiled_per_cycle=0,available_roles={"knacksaw_mana_engine","knacksaw_untap_engine","library_exile_outlet"},essential_card_ids=["clique"])); self.assertIsNone(p.prove_knacksaw_family(produced_mana=1,untap_cost=2,cards_exiled_per_cycle=1,available_roles={"knacksaw_mana_engine","knacksaw_untap_engine","library_exile_outlet"},essential_card_ids=["clique"]))


class Full99BridgeTests(unittest.TestCase):
    def test_live_v2_rows_bridge_to_exact_stable_v3(self):
        import tempfile
        from pathlib import Path
        from full99_telemetry_v3_bridge import attach_v3
        with tempfile.TemporaryDirectory() as td:
            deck=Path(td)/"deck.dck"; deck.write_text("[Commander]\n1 Kinnan, Bonder Prodigy\n\n[Main]\n"+"\n".join(f"1 Card {i}" for i in range(99))+"\n")
            v2=[]
            for i in range(99):
                v2.append({"card":f"Card {i}","openingHand":i==0,"kept":i==0,"mulliganed":False,"firstSeenTurn":1 if i==0 else None,"firstDrawnTurn":None,"zoneChanges":[],"tutored":False,"revealed":False,"cast":False,"played":False,"manaProduced":0,"manaSpent":0,"activated":False,"used":False,"comboParticipation":False,"protectionParticipation":False,"interactionParticipation":False,"attemptPresence":False,"protectedAttemptPresence":False,"naturalWinPresence":False,"packageExecution":False,"outcomeAttribution":"involved" if i==0 else "present"})
            compact={"variantDeckSha256":"deckhash","engineId":"engine","seed":1,"kinnanSeat":0,"podProfile":"balanced","cardTelemetryRows":v2,"rawActionTrace":[{"seq":1}]}
            out=attach_v3(compact,{},deck); self.assertTrue(out["telemetryV3Complete"]); self.assertEqual(len(out["cardTelemetryV3Rows"]),99); self.assertEqual(out["cardTelemetryV3Coverage"]["actualRows"],99); self.assertEqual(len(out["registeredCardIdentityMap"]),99)
    def test_bridge_rejects_partial_v2_rows(self):
        import tempfile
        from pathlib import Path
        from full99_telemetry_v3_bridge import attach_v3
        with tempfile.TemporaryDirectory() as td:
            deck=Path(td)/"deck.dck"; deck.write_text("[Commander]\n1 Kinnan, Bonder Prodigy\n\n[Main]\n"+"\n".join(f"1 Card {i}" for i in range(99))+"\n")
            with self.assertRaises(SemanticError): attach_v3({"variantDeckSha256":"d","cardTelemetryRows":[{"card":"Card 0"}]},{},deck)
    def test_neon_v3_builder_requires_complete_artifact_and_separates_trace(self):
        from build_full99_neon_ingest_v3 import build_sql
        cards=self.cards() if hasattr(self,"cards") else [{"registeredCardId":f"c{i}","cardName":f"Card {i}"} for i in range(99)]
        rows=build_full99_rows(game_id="g",deck_hash="d",registered_cards=cards,observed_by_card_id={})
        coverage=validate_full99_coverage(rows,valid_game_ids=["g"],registered_card_ids_by_game={"g":[c["registeredCardId"] for c in cards]})
        game={"telemetryV3Complete":True,"cardTelemetryV3Coverage":coverage,"cardTelemetryV3Rows":rows,"rawActionTrace":[{"seq":1}],"rawActionTraceHash":"h","rawActionTraceEventCount":1,"engineId":"e","variant":"v","seed":1,"kinnanSeat":0,"podProfile":"balanced","pilotVersion":"p"}
        sql=build_sql([game]); self.assertIn("sim_game_action_traces_v3",sql); self.assertIn("sim_game_card_telemetry_v3",sql); self.assertEqual(sql.count("kinnan-full99-card-telemetry-v3"),100)
        game["telemetryV3Complete"]=False
        with self.assertRaises(ValueError): build_sql([game])


class CardRegistrationParityTests(unittest.TestCase):
    def test_mdfc_lookup_preserves_exact_registered_identity(self):
        import kinnan_v9_forge_canary as c
        commanders, cards = c._parse_dck(
            c.DECK_DIR / "Kinnan_Sterling_TopDeck_Invitational_2026.dck",
            exact_kinnan_registration=True,
        )
        audit = c._registration_audit(commanders, cards)
        self.assertEqual(audit["registeredMainCount"], 99)
        self.assertEqual(audit["registeredDistinctMainCount"], 99)
        self.assertEqual(audit["mappedCardCount"], 5)
        glasspool = next(
            row for row in audit["registeredToEngine"]
            if row["registeredCardName"].startswith("Glasspool Mimic")
        )
        self.assertEqual(glasspool["registeredCardName"], "Glasspool Mimic // Glasspool Shore")
        self.assertEqual(glasspool["engineCardName"], "Glasspool Mimic")

    def test_unsupported_card_log_fails_closed_without_duplicates(self):
        import kinnan_v9_forge_canary as c
        stderr = (
            'An unsupported card was requested: "Missing" from "null".\n'
            'An unsupported card was requested: "Missing" from "null".\n'
        )
        self.assertEqual(c._unsupported_card_names(stderr), ["Missing"])


class ProductionParityAnchorTests(unittest.TestCase):
    def test_all_registered_anchor_files_are_exact_99(self):
        import kinnan_v9_production_parity_canary as p
        import kinnan_v9_forge_canary as c
        for deck in p.ANCHORS:
            commanders, cards = c._parse_dck(
                c.DECK_DIR / deck,
                exact_kinnan_registration=True,
            )
            self.assertEqual(len(commanders), 1, deck)
            self.assertEqual(len(cards) - len(commanders), 99, deck)
            self.assertEqual(len(set(cards[len(commanders):])), 99, deck)


class ForgePregamePromptTests(unittest.TestCase):
    def test_unscoped_choose_boolean_fails_closed(self):
        import kinnan_v9_forge_canary as c
        answer = c._pregame_answer({
            "type": "chooseBoolean",
            "confirmLabel": "Accept",
            "denyLabel": "Decline",
        })
        self.assertIsNone(answer)

    def test_choose_cards_max_zero_uses_forced_empty_choice(self):
        import kinnan_v9_forge_canary as c
        answer = c._pregame_answer({
            "type": "chooseCards",
            "min": 0,
            "max": 0,
            "cards": [{"id": "ignored"}],
        })
        self.assertEqual(
            answer,
            {
                "type": "chooseCards",
                "output": {
                    "type": "chooseCardsDecision",
                    "chosenCardIds": [],
                },
            },
        )

    def test_choose_cards_min_all_uses_forced_all_choice(self):
        import kinnan_v9_forge_canary as c
        answer = c._pregame_answer({
            "type": "chooseCards",
            "min": 2,
            "max": 2,
            "cards": [{"id": "first"}, {"id": "second"}],
        })
        self.assertEqual(
            answer,
            {
                "type": "chooseCards",
                "output": {
                    "type": "chooseCardsDecision",
                    "chosenCardIds": ["first", "second"],
                },
            },
        )

    def test_optional_selection_uses_protocol_v1_empty_decline(self):
        import kinnan_v9_forge_canary as c
        answer = c._pregame_answer({
            "type": "chooseFromSelection",
            "minTotal": 0,
            "maxTotal": 1,
            "options": [
                {"label": "Optional pregame effect", "weight": 1, "canRepeat": False},
            ],
        })
        self.assertEqual(
            answer,
            {
                "type": "chooseFromSelection",
                "output": {
                    "type": "selectionDecision",
                    "chosenIndices": [],
                },
            },
        )
        duplicate_mode = {
            "label": "Venom Blast — Artifacts and creatures your opponents control enter tapped.",
            "weight": 1,
            "canRepeat": False,
        }
        self.assertEqual(
            c._pregame_answer({
                "type": "chooseFromSelection",
                "minTotal": 1,
                "maxTotal": 1,
                "options": [duplicate_mode, dict(duplicate_mode)],
            }),
            {
                "type": "chooseFromSelection",
                "output": {
                    "type": "selectionDecision",
                    "chosenIndices": [0],
                },
            },
        )
        self.assertIsNone(c._pregame_answer({
            "type": "chooseFromSelection",
            "minTotal": 1,
            "maxTotal": 1,
            "options": [
                {"label": "Required mode", "weight": 1, "canRepeat": False},
            ],
        }))
        self.assertIsNone(c._pregame_answer({
            "type": "chooseFromSelection",
            "minTotal": 1,
            "maxTotal": 1,
            "options": [
                {"label": "Mode A", "weight": 1, "canRepeat": False},
                {"label": "Mode B", "weight": 1, "canRepeat": False},
            ],
        }))

    def test_empty_blockers_only_when_every_block_is_optional(self):
        import kinnan_v9_forge_canary as c

        prompt = {
            "type": "chooseBlockers",
            "attackers": [
                {
                    "attackerId": "first",
                    "validBlockerIds": ["blocker"],
                    "minBlockers": 1,
                    "mustBeBlocked": False,
                },
                {
                    "attackerId": "second",
                    "validBlockerIds": ["blocker"],
                    "minBlockers": 1,
                    "mustBeBlocked": False,
                },
            ],
            "availableBlockerIds": ["blocker"],
        }
        self.assertEqual(
            c._pregame_answer(prompt),
            {
                "type": "chooseBlockers",
                "output": {
                    "type": "declareBlockers",
                    "assignments": [],
                },
            },
        )
        prompt["attackers"][0]["mustBeBlocked"] = True
        self.assertIsNone(c._pregame_answer(prompt))

    def test_optional_land_entry_life_payment_declines_only_exact_prompt(self):
        witness = {
            "chosenActionLabel": "Play Garden of Freyalise",
            "chosenActionType": "cast",
        }
        prompt = {
            "type": "chooseBoolean",
            "confirmLabel": "Pay",
            "denyLabel": "Decline",
            "presentation": {
                "title": "Pay 3 {LIFE}?",
                "text": 'otherwise: "enters tapped."',
            },
        }
        self.assertEqual(
            _chosen_optional_entry_payment(prompt, witness),
            {
                "type": "chooseBoolean",
                "output": {"type": "decision", "value": False},
            },
        )

        for changed_witness, changed_prompt in (
            ({**witness, "chosenActionLabel": "Cast Some Spell"}, prompt),
            ({**witness, "chosenActionType": "activateAbility"}, prompt),
            (witness, {**prompt, "confirmLabel": "Accept"}),
            (
                witness,
                {
                    **prompt,
                    "presentation": {
                        "title": "Pay 3 {LIFE}?",
                        "text": "Choose a different optional effect.",
                    },
                },
            ),
        ):
            self.assertIsNone(
                _chosen_optional_entry_payment(changed_prompt, changed_witness)
            )

    def test_pay_mana_cost_uses_exact_engine_action_then_confirms(self):
        prompt = {
            "type": "payManaCost",
            "manaCost": "{1}{U}",
            "canConfirmFromPool": False,
            "actions": [
                {
                    "id": "tap:tropical:green",
                    "isManaAbility": True,
                    "cost": "{T}",
                    "producedMana": [{"color": "G", "amount": 1}],
                },
                {
                    "id": "tap:tropical:blue",
                    "isManaAbility": True,
                    "cost": "{T}",
                    "producedMana": [{"color": "U", "amount": 1}],
                },
                {
                    "id": "tap:pollinator:blue",
                    "isManaAbility": True,
                    "cost": "{T}, Tap an untapped Permanent you control",
                    "producedMana": [{"color": "U", "amount": 1}],
                },
            ],
        }
        self.assertEqual(
            _pay_mana_cost_answer(prompt),
            {
                "type": "payManaCost",
                "output": {
                    "type": "act",
                    "actionId": "tap:tropical:blue",
                },
            },
        )
        prompt["canConfirmFromPool"] = True
        self.assertEqual(
            _pay_mana_cost_answer(prompt),
            {
                "type": "payManaCost",
                "output": {"type": "pay", "auto": False},
            },
        )

    def test_pay_mana_cost_rejects_malformed_or_invented_actions(self):
        self.assertIsNone(_pay_mana_cost_answer({
            "type": "payManaCost",
            "manaCost": "{1}{U}",
            "canConfirmFromPool": False,
            "actions": [
                {
                    "id": "bad",
                    "isManaAbility": True,
                    "producedMana": [{"color": "U", "amount": 0}],
                },
                {
                    "id": "not-mana",
                    "isManaAbility": False,
                    "producedMana": [{"color": "U", "amount": 1}],
                },
            ],
        }))

    def test_cleanup_discard_uses_typed_pilot_keep_value(self):
        import kinnan_v9_forge_canary as c
        answer = c._pregame_answer({
            "type": "chooseCards",
            "min": 1,
            "max": 1,
            "presentation": {"title": "Discard"},
            "cards": [
                {
                    "id": "signet",
                    "cmc": 2,
                    "types": ["Artifact"],
                    "text": "{T}: Add one mana of any color.",
                },
                {
                    "id": "fae",
                    "cmc": 4,
                    "types": ["Creature"],
                    "text": "Flying. You may cast spells as though they had flash.",
                },
                {
                    "id": "archetype",
                    "cmc": 8,
                    "types": ["Enchantment", "Creature"],
                    "text": "Creatures you control have hexproof.",
                },
            ],
        })
        self.assertEqual(
            answer,
            {
                "type": "chooseCards",
                "output": {
                    "type": "chooseCardsDecision",
                    "chosenCardIds": ["fae"],
                },
            },
        )

    def test_choose_cards_with_real_or_malformed_choice_fails_closed(self):
        import kinnan_v9_forge_canary as c
        self.assertIsNone(c._pregame_answer({
            "type": "chooseCards",
            "min": 1,
            "max": 2,
            "cards": [{"id": "first"}, {"id": "second"}, {"id": "third"}],
        }))
        self.assertIsNone(c._pregame_answer({
            "type": "chooseCards",
            "min": 2,
            "max": 2,
            "cards": [{"id": "same"}, {"id": "same"}],
        }))

    def test_unknown_pregame_prompt_still_fails_closed(self):
        import kinnan_v9_forge_canary as c
        self.assertIsNone(c._pregame_answer({"type": "unknownPrompt"}))


class AdapterTests(unittest.TestCase):
    def test_choose_action_requires_and_uses_stable_action_id(self):
        import manabrew_pilot_v9 as p; snap={"phase":"main1","step":"main1","priorityPlayerId":"player-0"}; c=p.choose_action([{"actionId":"pass","type":"pass"},{"actionId":"mana","type":"activateAbility","isManaAbility":True,"cardTypes":["Creature"],"semanticTags":["mana_source"],"producedMana":{"G":1}}],snap,player_id="player-0"); self.assertEqual(c["actionId"],"mana")
    def test_missing_action_ids_fail_closed(self):
        import manabrew_pilot_v9 as p; snap={"phase":"main1","step":"main1","priorityPlayerId":"player-0"};
        with self.assertRaises(SemanticError): p.choose_action([{"type":"pass"}],snap,player_id="player-0")
    def test_production_ranking_fail_closed(self):
        import manabrew_pilot_v9 as p; self.assertFalse(p.production_ranking_ready());
        with self.assertRaises(RuntimeError): p.assert_ranking_ready()


class LiveForgeCausalityTests(unittest.TestCase):
    def test_material_snapshot_ignores_only_temporal_priority_fields(self):
        base = {
            "turn": 1,
            "step": "main1",
            "activePlayerId": "player-0",
            "priorityPlayerId": "player-0",
            "players": [{"id": "player-0", "life": 40, "manaPool": {"G": 0}}],
            "zones": [{"ownerId": "player-0", "zone": "hand", "cards": [{"id": "c1"}]}],
            "stack": [],
            "combatAssignments": [],
            "gameOver": False,
            "dayTime": None,
        }
        temporal = dict(base, turn=2, step="draw", activePlayerId="player-1", priorityPlayerId="player-2")
        self.assertEqual(_stable_hash(_material_snapshot(base)), _stable_hash(_material_snapshot(temporal)))

    def test_material_snapshot_detects_mana_or_zone_effect(self):
        base = {
            "players": [{"id": "player-0", "life": 40, "manaPool": {"G": 0}}],
            "zones": [{"ownerId": "player-0", "zone": "hand", "cards": [{"id": "esg"}]}],
            "stack": [],
        }
        changed = {
            **base,
            "players": [{"id": "player-0", "life": 40, "manaPool": {"G": 1}}],
            "zones": [{"ownerId": "player-0", "zone": "exile", "cards": [{"id": "esg"}]}],
        }
        self.assertNotEqual(_stable_hash(_material_snapshot(base)), _stable_hash(_material_snapshot(changed)))

    def test_only_selected_action_cost_confirmation_is_accepted(self):
        witness = {
            "chosenActionDescription": "Exile Elvish Spirit Guide from your hand: Add {G}.",
        }
        prompt = {
            "type": "chooseBoolean",
            "presentation": {"title": "Exile Elvish Spirit Guide from your hand"},
            "confirmLabel": "Accept",
            "denyLabel": "Decline",
        }
        self.assertTrue(_chosen_cost_confirmation(prompt, witness)["output"]["value"])
        unrelated = {**prompt, "presentation": {"title": "Pay 2 life"}}
        self.assertIsNone(_chosen_cost_confirmation(unrelated, witness))
        self.assertIsNone(_chosen_cost_confirmation(prompt, None))

    def test_semantic_trace_ignores_empty_priority_sampling_only(self):
        first = [
            {"promptId": 1, "promptType": "chooseAction", "turn": 1, "step": "main1", "forcedPass": True, "snapshot": {"x": 1}, "snapshotHash": "a"},
            {"promptId": 2, "promptType": "chooseAction", "turn": 1, "step": "main1", "submittedAnswer": {"output": {"type": "act"}}},
        ]
        second = [
            {"promptId": 1, "promptType": "chooseAction", "turn": 1, "step": "combatBegin", "forcedPass": True, "snapshot": {"x": 2}, "snapshotHash": "b"},
            {"promptId": 2, "promptType": "chooseAction", "turn": 1, "step": "main1", "submittedAnswer": {"output": {"type": "act"}}},
        ]
        self.assertEqual(_semantic_prompt_trace(first), _semantic_prompt_trace(second))
        second[1]["step"] = "main2"
        self.assertNotEqual(_semantic_prompt_trace(first), _semantic_prompt_trace(second))


class KinnanTurnHorizonTests(unittest.TestCase):
    def test_global_turn_twelve_is_not_kinnan_turn_four(self):
        observed: set[int] = set()
        snapshots = [
            {"turn": 1, "step": "upkeep", "activePlayerId": "player-3"},
            {"turn": 2, "step": "upkeep", "activePlayerId": "player-0"},
            {"turn": 6, "step": "upkeep", "activePlayerId": "player-0"},
            {"turn": 10, "step": "endOfTurn", "activePlayerId": "player-0"},
            {"turn": 12, "step": "upkeep", "activePlayerId": "player-2"},
        ]
        for snapshot in snapshots:
            self.assertFalse(
                _kinnan_horizon_reached(snapshot, observed, 4)
            )
        self.assertEqual(observed, {2, 6, 10})
        self.assertFalse(
            _kinnan_horizon_reached(
                {
                    "turn": 14,
                    "step": "upkeep",
                    "activePlayerId": "player-0",
                },
                observed,
                4,
            )
        )
        self.assertTrue(
            _kinnan_horizon_reached(
                {
                    "turn": 14,
                    "step": "endOfTurn",
                    "activePlayerId": "player-0",
                },
                observed,
                4,
            )
        )


class LiveFull99ExtractionTests(unittest.TestCase):
    def test_snapshot_rows_preserve_99_and_observed_semantics(self):
        import kinnan_v9_forge_canary as canary
        import kinnan_v9_production_parity_canary as parity
        deck = canary.DECK_DIR / parity.ANCHORS[0]
        commanders, cards = canary._parse_dck(deck, exact_kinnan_registration=True)
        opening = cards[len(commanders):len(commanders) + 7]
        hand = [
            {"id": f"engine-{index}", "identity": {"name": canary._engine_name(name)}}
            for index, name in enumerate(opening)
        ]
        witness = {
            "materialActionEffectConfirmed": True,
            "witness": {"promptId": 2, "chosenActionId": "prompt-action-0"},
            "promptTrace": [
                {
                    "promptId": 1,
                    "promptType": "mulligan",
                    "submittedAnswer": {"output": {"keep": True}},
                    "snapshot": {
                        "turn": 0,
                        "step": "untap",
                        "zones": [{"ownerId": "player-0", "zone": "hand", "cards": hand}],
                    },
                },
                {
                    "promptId": 2,
                    "promptType": "chooseAction",
                    "promptInput": {
                        "actions": [{
                            "id": "prompt-action-0",
                            "cardId": "engine-0",
                            "type": "cast",
                        }],
                    },
                    "snapshot": {
                        "turn": 1,
                        "step": "main1",
                        "zones": [{"ownerId": "player-0", "zone": "hand", "cards": hand}],
                    },
                },
            ],
        }
        rows, coverage = parity._registered_rows(
            deck, seed=7, replay=1, witness=witness
        )
        self.assertEqual(len(rows), 99)
        self.assertTrue(coverage["valid"])
        self.assertEqual(coverage["openingHandRows"], 7)
        self.assertEqual(coverage["keptRows"], 7)
        self.assertEqual(coverage["observedCardRows"], 7)
        self.assertTrue(coverage["selectedActionAttributed"])
        first = next(row for row in rows if row["registeredCardName"] == opening[0])
        self.assertTrue(first["openingHand"])
        self.assertTrue(first["kept"])
        self.assertTrue(first["cast"])
        self.assertTrue(first["played"])
        unseen = next(row for row in rows if row["registeredCardName"] not in opening)
        self.assertFalse(unseen["present"])
        self.assertEqual(unseen["zones"], [])


class LiveManaPaymentExtractionTests(unittest.TestCase):
    def test_confirmed_pool_depletion_is_attributed_to_exact_card(self):
        import kinnan_v9_forge_canary as canary
        import kinnan_v9_production_parity_canary as parity

        deck = canary.DECK_DIR / parity.ANCHORS[0]
        commanders, cards = canary._parse_dck(
            deck, exact_kinnan_registration=True
        )
        opening = cards[len(commanders):len(commanders) + 7]
        hand = [
            {
                "id": f"engine-{index}",
                "identity": {"name": canary._engine_name(name)},
            }
            for index, name in enumerate(opening)
        ]
        witness = {
            "materialActionEffectConfirmed": True,
            "promptTrace": [
                {
                    "promptId": 1,
                    "promptType": "mulligan",
                    "submittedAnswer": {"output": {"keep": True}},
                    "snapshot": {
                        "turn": 0,
                        "step": "untap",
                        "players": [
                            {"id": "player-0", "manaPool": {"U": 0}}
                        ],
                        "zones": [
                            {
                                "ownerId": "player-0",
                                "zone": "hand",
                                "cards": hand,
                            }
                        ],
                    },
                },
                {
                    "promptId": 2,
                    "promptType": "chooseAction",
                    "promptInput": {
                        "actions": [
                            {
                                "id": "cast-card",
                                "cardId": "engine-0",
                                "type": "cast",
                            }
                        ],
                    },
                    "submittedAnswer": {
                        "output": {"type": "act", "actionId": "cast-card"}
                    },
                    "snapshot": {
                        "turn": 1,
                        "step": "main1",
                        "players": [
                            {"id": "player-0", "manaPool": {"U": 2}}
                        ],
                        "zones": [
                            {
                                "ownerId": "player-0",
                                "zone": "hand",
                                "cards": hand,
                            }
                        ],
                    },
                },
                {
                    "promptId": 3,
                    "promptType": "payManaCost",
                    "promptInput": {
                        "cardId": "engine-0",
                        "canConfirmFromPool": True,
                    },
                    "submittedAnswer": {
                        "output": {"type": "pay", "auto": False}
                    },
                    "snapshot": {
                        "turn": 1,
                        "step": "main1",
                        "players": [
                            {"id": "player-0", "manaPool": {"U": 2}}
                        ],
                        "zones": [
                            {
                                "ownerId": "player-0",
                                "zone": "hand",
                                "cards": hand,
                            }
                        ],
                    },
                },
                {
                    "promptId": 4,
                    "promptType": "chooseAction",
                    "promptInput": {"actions": []},
                    "snapshot": {
                        "turn": 1,
                        "step": "main1",
                        "players": [
                            {"id": "player-0", "manaPool": {"U": 0}}
                        ],
                        "zones": [
                            {
                                "ownerId": "player-0",
                                "zone": "hand",
                                "cards": hand,
                            }
                        ],
                    },
                },
            ],
        }
        rows, coverage = parity._registered_rows(
            deck, seed=9, replay=1, witness=witness
        )
        paid = next(
            row for row in rows
            if row["registeredCardName"] == opening[0]
        )
        self.assertTrue(coverage["valid"])
        self.assertEqual(coverage["observedManaPaymentCount"], 1)
        self.assertEqual(coverage["observedManaSpentTotal"], 2)
        self.assertEqual(paid["manaSpent"], 2)
        self.assertTrue(paid["involved"])

    def test_unconfirmed_or_non_depleting_pool_is_not_inferred(self):
        import kinnan_v9_production_parity_canary as parity

        self.assertEqual(
            parity._player_mana_total(
                {"players": [{"id": "player-0", "manaPool": {"U": 2, "G": 1}}]}
            ),
            3,
        )
        self.assertIsNone(
            parity._player_mana_total(
                {"players": [{"id": "player-1", "manaPool": {"U": 2}}]}
            )
        )


class LiveRevealExtractionTests(unittest.TestCase):
    def test_exact_player_reveal_is_attributed_without_library_view_false_positive(self):
        import kinnan_v9_forge_canary as canary
        import kinnan_v9_production_parity_canary as parity

        deck = canary.DECK_DIR / parity.ANCHORS[0]
        commanders, cards = canary._parse_dck(
            deck, exact_kinnan_registration=True
        )
        main = cards[len(commanders):]
        opening = main[:7]
        revealed_name = main[7]
        browser_only_name = main[8]
        hand = [
            {
                "id": f"engine-{index}",
                "identity": {"name": canary._engine_name(name)},
            }
            for index, name in enumerate(opening)
        ]
        witness = {
            "materialActionEffectConfirmed": True,
            "promptTrace": [
                {
                    "promptId": 1,
                    "promptType": "mulligan",
                    "submittedAnswer": {"output": {"keep": True}},
                    "snapshot": {
                        "turn": 0,
                        "step": "untap",
                        "zones": [
                            {
                                "ownerId": "player-0",
                                "zone": "hand",
                                "cards": hand,
                            }
                        ],
                    },
                },
                {
                    "promptId": 2,
                    "promptType": "revealCards",
                    "turn": 1,
                    "step": "main1",
                    "promptInput": {
                        "ownerPlayerId": "player-view-0",
                        "zone": "library",
                        "cards": [
                            {
                                "id": "browser-only",
                                "identity": {
                                    "name": canary._engine_name(browser_only_name)
                                },
                            }
                        ],
                    },
                },
                {
                    "promptId": 3,
                    "promptType": "revealCards",
                    "turn": 1,
                    "step": "main1",
                    "promptInput": {
                        "ownerPlayerId": "player-0",
                        "zone": "library",
                        "cards": [
                            {
                                "id": "revealed-card",
                                "identity": {
                                    "name": canary._engine_name(revealed_name)
                                },
                            }
                        ],
                    },
                },
                {
                    "promptId": 4,
                    "promptType": "chooseAction",
                    "promptInput": {
                        "actions": [
                            {
                                "id": "prompt-action-0",
                                "cardId": "engine-0",
                                "type": "cast",
                            }
                        ],
                    },
                    "submittedAnswer": {
                        "output": {
                            "type": "act",
                            "actionId": "prompt-action-0",
                        }
                    },
                    "snapshot": {
                        "turn": 1,
                        "step": "main1",
                        "zones": [
                            {
                                "ownerId": "player-0",
                                "zone": "hand",
                                "cards": hand,
                            }
                        ],
                    },
                },
            ],
        }
        rows, coverage = parity._registered_rows(
            deck, seed=8, replay=1, witness=witness
        )
        revealed = next(
            row for row in rows
            if row["registeredCardName"] == revealed_name
        )
        browser_only = next(
            row for row in rows
            if row["registeredCardName"] == browser_only_name
        )
        self.assertTrue(coverage["valid"])
        self.assertEqual(coverage["observedRevealCount"], 1)
        self.assertTrue(revealed["present"])
        self.assertTrue(revealed["revealed"])
        self.assertTrue(revealed["involved"])
        self.assertEqual(revealed["zones"], ["library"])
        self.assertFalse(browser_only["present"])
        self.assertFalse(browser_only["revealed"])


class PhaseAwareLiveActionTests(unittest.TestCase):
    def test_mana_action_outside_main_phase_yields_policy_pass(self):
        import manabrew_pilot_v9 as pilot
        action = {
            "id": "tap-land",
            "type": "activateAbility",
            "isManaAbility": True,
            "producedMana": [{"color": "U", "amount": 1}],
        }
        chosen = pilot.choose_action(
            [action],
            {
                "step": "upkeep",
                "priorityPlayerId": "player-0",
            },
            player_id="player-0",
        )
        self.assertIsNone(chosen)

    def test_main_phase_mana_action_remains_selectable(self):
        import manabrew_pilot_v9 as pilot
        action = {
            "id": "tap-land",
            "type": "activateAbility",
            "isManaAbility": True,
            "producedMana": [{"color": "U", "amount": 1}],
        }
        chosen = pilot.choose_action(
            [action],
            {
                "step": "main1",
                "priorityPlayerId": "player-0",
            },
            player_id="player-0",
        )
        self.assertEqual(chosen["id"], "tap-land")

    def test_undo_mana_is_never_a_forward_pilot_action(self):
        import manabrew_pilot_v9 as pilot
        chosen = pilot.choose_action(
            [{"id": "undo", "type": "undoMana"}],
            {
                "step": "main1",
                "priorityPlayerId": "player-0",
            },
            player_id="player-0",
        )
        self.assertIsNone(chosen)


class ProductionParityCliContractTests(unittest.TestCase):
    def test_player_specific_horizon_is_parsed_and_forwarded(self):
        source = (Path(__file__).resolve().parent / "kinnan_v9_production_parity_canary.py").read_text()
        self.assertIn('"--horizon-kinnan-turn"', source)
        self.assertIn(
            "horizon_kinnan_turn=args.horizon_kinnan_turn",
            source,
        )


if __name__ == "__main__": unittest.main(verbosity=2)
