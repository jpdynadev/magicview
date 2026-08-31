#!/usr/bin/env python3
from __future__ import annotations
import unittest

from kinnan_semantics_v9 import *


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


class AdapterTests(unittest.TestCase):
    def test_choose_action_requires_and_uses_stable_action_id(self):
        import manabrew_pilot_v9 as p; snap={"phase":"main1","step":"main1","priorityPlayerId":"player-0"}; c=p.choose_action([{"actionId":"pass","type":"pass"},{"actionId":"mana","type":"activateAbility","isManaAbility":True,"cardTypes":["Creature"],"semanticTags":["mana_source"],"producedMana":{"G":1}}],snap,player_id="player-0"); self.assertEqual(c["actionId"],"mana")
    def test_missing_action_ids_fail_closed(self):
        import manabrew_pilot_v9 as p; snap={"phase":"main1","step":"main1","priorityPlayerId":"player-0"};
        with self.assertRaises(SemanticError): p.choose_action([{"type":"pass"}],snap,player_id="player-0")
    def test_production_ranking_fail_closed(self):
        import manabrew_pilot_v9 as p; self.assertFalse(p.production_ranking_ready());
        with self.assertRaises(RuntimeError): p.assert_ranking_ready()


if __name__ == "__main__": unittest.main(verbosity=2)
