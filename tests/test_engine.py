import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from afgooien.engine import Dart, Game, GameError  # noqa: E402


def d(label: str, x=None, y=None) -> dict:
    """'T20', 'D5', 'S1', 'B' (bull), 'BE' (bullseye), 'M' (mis)."""
    if label == "M":
        return {"number": 0, "multiplier": 0}
    if label in ("B", "BE"):
        out = {"number": 25, "multiplier": 2 if label == "BE" else 1}
    else:
        out = {"number": int(label[1:]), "multiplier": "SDT".index(label[0]) + 1}
    if x is not None:
        out["x"], out["y"] = x, y
    return out


CLASSIC = {"miss_penalty": False, "bull_bonus": False, "ton_bonus": False}


def give(g, i, pts):
    """Zet een speler direct op een aantal punten (voor tests)."""
    g.players[i].points = pts
    g.players[i].scored = pts > 0 or g.players[i].scored


def setup_game(names=("Ann", "Bob"), numbers=(20, 14), bulls=(0.05, 0.2), extra=False, **settings) -> Game:
    g = Game()
    g.new_game(list(names), {**({} if extra else CLASSIC), **settings})
    for num, b in zip(numbers, bulls):
        g.throw(d(f"S{num}"))
        g.throw(d("S20", b, 0.0) if b else d("M"))
        g.takeout()
    assert g.phase == "play", g.log
    return g


class SelectTests(unittest.TestCase):
    def test_need_two_players(self):
        with self.assertRaises(GameError):
            Game().new_game(["Solo"])

    def test_bull_and_miss_rethrow(self):
        g = Game()
        g.new_game(["Ann", "Bob"])
        g.throw(d("BE"))
        g.throw(d("M"))
        self.assertIsNone(g.players[0].number)
        g.throw(d("T7"))
        self.assertEqual(g.players[0].number, 7)
        self.assertEqual(g.sel_step, "bull")

    def test_taken_number_rethrow(self):
        g = Game()
        g.new_game(["Ann", "Bob"])
        g.throw(d("S20"))
        g.throw(d("BE", 0, 0))
        g.takeout()
        g.throw(d("D20"))
        self.assertIsNone(g.players[1].number)
        g.throw(d("S3"))
        self.assertEqual(g.players[1].number, 3)

    def test_next_blocked_until_done(self):
        g = Game()
        g.new_game(["Ann", "Bob"])
        self.assertFalse(g.next_player())
        g.throw(d("S1"))
        self.assertFalse(g.next_player())

    def test_order_by_distance(self):
        g = setup_game(("Ann", "Bob", "Cas"), (1, 2, 3), (0.3, 0.02, 0.1))
        self.assertEqual([g.players[i].name for i in g.order], ["Bob", "Cas", "Ann"])
        self.assertEqual(g.players[g.current].name, "Bob")

    def test_tiebreak(self):
        g = Game()
        g.new_game(["Ann", "Bob", "Cas"])
        for num in (1, 2, 3):
            g.throw(d(f"S{num}"))
            g.throw(d("B") if num != 3 else d("S5"))   # Ann en Bob gelijk (bull zonder positie)
            g.takeout()
        self.assertEqual(g.phase, "select")
        self.assertEqual(g.sel_queue, [0, 1])
        g.throw(d("S20", 0.3, 0)); g.takeout()
        g.throw(d("S20", 0.1, 0)); g.takeout()
        self.assertEqual(g.phase, "play")
        self.assertEqual([g.players[i].name for i in g.order], ["Bob", "Ann", "Cas"])


class PlayTests(unittest.TestCase):
    def test_points_capped(self):
        g = setup_game()
        ann = g.players[0]
        g.throw(d("T20")); g.throw(d("T20"))
        self.assertEqual(ann.points, 5)
        self.assertTrue(ann.reached_target)

    def test_not_killer_cannot_hit_others(self):
        g = setup_game()
        g.throw(d("T20")); g.throw(d("T14"))
        self.assertFalse(g.players[1].out)
        self.assertEqual(g.players[1].points, 0)

    def test_killer_same_turn_and_any_rule(self):
        g = setup_game()
        g.throw(d("T20")); g.throw(d("D20"))   # 5 punten
        g.throw(d("S14"))                       # Bob staat op 0 → af (regel: iedereen)
        self.assertTrue(g.players[1].out)
        self.assertEqual(g.phase, "finished")
        self.assertEqual(g.winner, 0)

    def test_rule_reached_target(self):
        g = setup_game(elimination="reached_target")
        g.throw(d("T20")); g.throw(d("D20")); g.throw(d("T14"))
        self.assertFalse(g.players[1].out)
        self.assertEqual(g.phase, "play")

    def test_knock_down_and_rebuild(self):
        g = setup_game(("Ann", "Bob", "Cas"), (20, 14, 3), (0.05, 0.2, 0.3))
        g.throw(d("T20")); g.throw(d("D20")); g.takeout()          # Ann 5
        g.throw(d("T14")); g.throw(d("D14")); g.takeout()          # Bob 5
        g.throw(d("S3")); g.takeout()                              # Cas 1
        g.throw(d("D14")); g.throw(d("S14")); g.takeout()          # Ann: Bob 5 → 2
        bob = g.players[1]
        self.assertEqual(bob.points, 2)
        g.throw(d("D20"))                                          # Bob is geen afgooier meer
        self.assertEqual(g.players[0].points, 5)
        g.throw(d("D14"))                                          # Bob terug op 4
        g.throw(d("T14"))                                          # 5 (max)
        self.assertEqual(bob.points, 5)

    def test_own_number_at_target_does_nothing(self):
        g = setup_game()
        g.throw(d("T20")); g.throw(d("D20")); g.throw(d("T20"))
        self.assertEqual(g.players[0].points, 5)

    def test_max_darts_per_turn(self):
        g = setup_game()
        for _ in range(3):
            g.throw(d("M"))
        self.assertFalse(g.throw(d("T20")))
        self.assertEqual(g.players[0].points, 0)

    def test_overkill_floors_at_zero(self):
        g = setup_game(("Ann", "Bob", "Cas"), (20, 14, 3), (0.05, 0.2, 0.3))
        g.throw(d("T20")); g.throw(d("D20")); g.takeout()
        g.throw(d("S14")); g.takeout()                              # Bob 1
        g.takeout()                                                 # Cas: geen pijlen → genegeerd
        g.next_player()                                             # Cas slaat over
        g.throw(d("T14"))
        self.assertTrue(g.players[1].out)
        self.assertEqual(g.players[1].points, 0)
        self.assertEqual(g.players[1].place, 3)
        g.takeout()
        self.assertEqual(g.players[g.current].name, "Cas")         # Bob wordt overgeslagen

    def test_undo_restores(self):
        g = setup_game()
        g.throw(d("T20"))
        g.throw(d("D20"))
        g.throw(d("S14"))
        self.assertEqual(g.phase, "finished")
        g.undo()
        self.assertEqual(g.phase, "play")
        self.assertFalse(g.players[1].out)
        self.assertEqual(g.players[0].points, 5)
        self.assertEqual(len(g.turn_darts), 2)

    def test_reload_events(self):
        g = setup_game()
        g.throw(d("T20"))
        h = Game()
        h.load_events(g.events)
        self.assertEqual(h.state()["players"], g.state()["players"])
        self.assertEqual(h.announce, [])

    def test_dart_validation(self):
        with self.assertRaises(GameError):
            Dart.from_dict({"number": 21, "multiplier": 1})
        with self.assertRaises(GameError):
            Dart.from_dict({"number": 25, "multiplier": 3})


class ExtraRuleTests(unittest.TestCase):
    def three(self):
        return setup_game(("Ann", "Bob", "Cas"), (20, 14, 3), (0.05, 0.2, 0.3), extra=True)

    def test_miss_penalty_floor_zero(self):
        g = self.three()
        ann = g.players[0]
        g.throw(d("M"))
        self.assertEqual(ann.points, 0)
        self.assertFalse(ann.out)
        g.throw(d("D20")); g.throw(d("M"))
        self.assertEqual(ann.points, 1)

    def test_miss_on_board_no_penalty(self):
        g = self.three()
        g.throw(d("D20")); g.throw(d("S20"))                         # Ann 3
        g.throw({"number": 0, "multiplier": 0, "x": 0.0, "y": 1.1})  # in de cijferring: mis, geen strafpunt
        self.assertEqual(g.players[0].points, 3)
        self.assertEqual(g.players[0].outside, 0)
        g.takeout(); g.takeout(); g.next_player(); g.next_player()
        g.throw({"number": 0, "multiplier": 0, "x": 0.0, "y": 1.4})  # naast het hele bord: −1
        self.assertEqual(g.players[0].points, 2)
        self.assertEqual(g.players[0].outside, 1)

    def test_miss_drops_killer(self):
        g = setup_game(("Ann", "Bob", "Cas"), (1, 14, 3), (0.05, 0.2, 0.3), extra=True)
        g.throw(d("T1")); g.throw(d("D1")); g.takeout()             # Ann 5
        g.throw(d("S14")); g.takeout()                              # Bob 1
        g.throw(d("S3")); g.takeout()                               # Cas 1
        g.throw(d("M"))                                             # Ann 4: geen afgooier meer
        self.assertEqual(g.players[0].points, 4)
        g.throw(d("S14"))
        self.assertEqual(g.players[1].points, 1)
        g.throw(d("S1"))                                            # weer 5
        self.assertEqual(g.players[0].points, 5)

    def test_bull_to_self_when_building(self):
        g = self.three()
        g.throw(d("BE"))
        self.assertEqual(g.players[0].points, 3)
        g.throw(d("B"))
        self.assertEqual(g.players[0].points, 4)
        self.assertFalse(g.pending)

    def test_bull_distribution_split(self):
        g = self.three()
        give(g, 0, 5); give(g, 1, 2); give(g, 2, 2)
        g.throw(d("T20")); g.throw(d("D20"))                        # al op 5, 100 → bonus 3 verdelen
        self.assertEqual(g.pending[0]["points"], 3)
        with self.assertRaises(GameError):
            g.allocate({1: 2})                                      # te weinig
        with self.assertRaises(GameError):
            g.allocate({0: 3})                                      # jezelf
        self.assertFalse(g.next_player())                           # eerst kiezen
        g.allocate({1: 2, 2: 1})                                    # Ann zet Bob op 0: af; Cas houdt 1
        self.assertEqual((g.players[1].points, g.players[2].points), (0, 1))
        self.assertTrue(g.players[1].out)
        self.assertEqual(g.phase, "play")

    def test_one_opponent_no_choice(self):
        g = self.three()
        give(g, 0, 5); give(g, 1, 2); give(g, 2, 3)
        g.throw(d("T20")); g.throw(d("S20"))                        # Ann al op 5 (80)
        g.throw(d("S20"))                                           # 100 → 2 tegenstanders met punten: kiezen
        g.allocate([[1, 1], [2, 2]])                                # Bob 1, Cas 1
        self.assertEqual((g.players[1].points, g.players[2].points), (1, 1))
        g.takeout()
        g.throw(d("S14")); g.takeout()                              # Bob 2
        g.throw(d("T3")); g.takeout()                               # Cas 4
        g.throw(d("D14"))                                           # Ann raakt Bob: 0 → af
        self.assertTrue(g.players[1].out)
        g.throw(d("BE"))                                            # nog maar één tegenstander → direct
        self.assertFalse(g.pending)
        self.assertEqual(g.players[2].points, 1)
        self.assertEqual(g.state()["fx"][0]["type"], "bull")

    def test_queue_while_choosing(self):
        g = setup_game(("Ann", "Bob", "Cas", "Dirk"), (20, 14, 3, 7), (0.05, 0.2, 0.3, 0.4), extra=True)
        for i in (1, 2, 3):
            give(g, i, 1)
        give(g, 0, 5)
        g.throw(d("T20")); g.throw(d("D20")); g.takeout()           # Ann al op 5, 100 → kiezen
        self.assertTrue(g.pending)
        g.allocate({1: 1, 2: 1, 3: 1})                              # Ann zet iedereen op 0: allemaal af
        self.assertEqual(g.phase, "finished")
        self.assertEqual(g.winner, 0)

    def test_queue_darts_wait(self):
        g = setup_game(("Ann", "Bob", "Cas"), (20, 14, 3), (0.05, 0.2, 0.3), extra=True, elimination="reached_target")
        g.throw(d("D20")); g.throw(d("D20")); g.takeout()           # Ann 4
        g.throw(d("T14")); g.throw(d("D14")); g.takeout()           # Bob 5
        g.throw(d("T3")); g.throw(d("D3")); g.takeout()             # Cas 5
        g.throw(d("S20"))                                           # Ann 5
        g.throw(d("BE"))                                            # 3 verdelen (2 tegenstanders)
        self.assertEqual(g.state()["pending"]["reason"], "Bullseye")
        g.throw(d("S3"))                                            # wacht in de rij
        self.assertEqual(len(g.turn_darts), 2)
        self.assertEqual(g.state()["queued"], 1)
        g.allocate({2: 3})                                          # Cas 2, daarna S3 → 1
        self.assertEqual(g.players[2].points, 1)
        self.assertEqual(len(g.turn_darts), 3)
        g.undo()
        self.assertTrue(g.pending)
        self.assertEqual(g.players[2].points, 5)

    def test_fx_and_announce_live_only(self):
        g = setup_game(extra=True)
        g.throw(d("T20")); g.throw(d("D20"))                        # 5 + 100; Bob op 0: bonus vervalt
        self.assertEqual([f["type"] for f in g.state()["fx"]], ["killer", "ton"])
        g.throw(d("S14"))                                           # echte treffer: Bob af
        kinds = [f["type"] for f in g.state()["fx"]]
        self.assertEqual(kinds, ["out", "win"])
        self.assertIn("Game shot, en de wedstrijd! Ann wint!", g.state()["announce"])
        self.assertTrue(any("wins" in a for a in g.state("en")["announce"]))
        g.undo()
        self.assertEqual(g.state()["fx"], [])

    def test_ton_bonus_once_and_to_self(self):
        g = setup_game(("Ann", "Bob"), (1, 14), (0.05, 0.2), extra=True)
        g.throw(d("T20")); g.throw(d("T20"))                        # 120 → +3 voor Ann
        self.assertEqual(g.players[0].points, 3)
        g.throw(d("T20"))                                           # 180, geen tweede bonus
        self.assertEqual(g.players[0].points, 3)

    def test_bonus_cap(self):
        g = self.three()
        give(g, 1, 2); give(g, 2, 2)
        g.throw(d("D20")); g.throw(d("D20"))                        # 4
        g.throw(d("BE"))                                            # +1 (max), 130: pas net op 5 → geen afgooien
        self.assertEqual(g.players[0].points, 5)
        self.assertFalse(g.pending)
        self.assertEqual((g.players[1].points, g.players[2].points), (2, 2))

    def test_bonus_on_reaching_five_goes_to_self_only(self):
        g = self.three()
        give(g, 0, 3); give(g, 1, 2); give(g, 2, 2)
        g.throw(d("BE"))                                            # 3 + bullseye → 5 (1 vervalt), niemand iets kwijt
        self.assertEqual(g.players[0].points, 5)
        self.assertFalse(g.pending)
        self.assertEqual((g.players[1].points, g.players[2].points), (2, 2))
        g.throw(d("S14"))                                           # volgende pijl: wel afgooien
        self.assertEqual(g.players[1].points, 1)
        g.throw(d("B"))                                             # bull nu als afgooier: verdelen (2 met punten)
        self.assertEqual(g.pending[0]["points"], 1)

    def test_ton_on_dart_that_reaches_five(self):
        g = self.three()
        give(g, 0, 4); give(g, 1, 2); give(g, 2, 2)
        g.throw(d("T20")); g.throw(d("S20"))                        # T20 → 5 (60), S20 → 80
        g.throw(d("S20"))                                           # 100: al op 5 vóór deze pijl → verdelen
        self.assertEqual(g.pending[0]["points"], 3)
        g2 = self.three()
        give(g2, 0, 4); give(g2, 1, 2); give(g2, 2, 2)
        g2.throw(d("T18")); g2.throw(d("T20"))                      # T20 → 5 én 114 met dezelfde pijl: niets afhalen
        self.assertFalse(g2.pending)
        self.assertEqual((g2.players[1].points, g2.players[2].points), (2, 2))


class StatsTests(unittest.TestCase):
    def test_stats_and_summary(self):
        g = setup_game(extra=True)                        # Ann 20, Bob 14
        g.throw(d("T20")); g.throw(d("M")); g.throw(d("S1")); g.takeout()     # Ann: 3 pt, 1 buiten, 1 nutteloos
        g.throw(d("T14")); g.throw(d("D14")); g.takeout()                     # Bob 5
        g.throw(d("T20")); g.throw(d("T20"))                                  # Ann 5; 120 → Bob −3 → 2
        g.throw(d("T20"))                                                     # 180 (eigen nummer telt niet meer)
        ann = g.players[0]
        self.assertEqual((ann.darts, ann.useful, ann.outside, ann.triples), (6, 2, 1, 4))
        self.assertEqual((ann.tons, ann.n180, ann.max_turn, ann.score_total), (1, 1, 180, 241))
        self.assertEqual(ann.darts_to_target, 4)
        self.assertIsNone(g.summary())
        g.takeout(); g.throw(d("M")); g.takeout()                             # Bob
        g.throw(d("D14"))                                                     # Bob af
        sm = g.summary()
        self.assertEqual(sm["winner"], "Ann")
        self.assertEqual([q["name"] for q in sm["players"]], ["Ann", "Bob"])
        self.assertEqual(sm["players"][0]["useful"], 3)
        self.assertEqual(sm["players"][1]["place"], 2)

class CorrectTests(unittest.TestCase):
    def test_correct_number_in_select(self):
        g = Game()
        g.new_game(["Ann", "Bob"])
        g.throw(d("S5"))                                   # Autodarts zag S5, maar het was mis
        self.assertEqual(g.players[0].number, 5)
        g.correct(0, d("M"))
        self.assertIsNone(g.players[0].number)
        self.assertEqual(g.sel_step, "number")
        g.throw(d("S7"))
        self.assertEqual(g.players[0].number, 7)

    def test_correct_dart_in_turn_recomputes(self):
        g = setup_game(extra=True)                         # Ann 20, Bob 14
        g.throw(d("S20")); g.throw(d("S1")); g.throw(d("S20"))
        self.assertEqual(g.players[0].points, 2)
        g.correct(1, {"number": 20, "multiplier": 3, "x": 0.0, "y": 0.6})   # tweede pijl was T20
        self.assertEqual(g.players[0].points, 5)
        self.assertEqual([x.label for x in g.turn_darts], ["S20", "T20", "S20"])
        self.assertIn("aangepast", g.state()["notice"])
        self.assertIn("changed", g.state("en")["notice"])
        g.undo()                                           # ongedaan maken haalt de laatste pijl weg
        self.assertEqual([x.label for x in g.turn_darts], ["S20", "T20"])

    def test_correct_winning_dart_after_finish(self):
        g = setup_game(extra=True)
        g.throw(d("T20")); g.throw(d("D20")); g.throw(d("S14"))   # 5 punten, dan Bob geraakt → af
        self.assertEqual(g.phase, "finished")
        g.correct(1, d("S20"))                             # was eigenlijk S20 → 4 punten, Bob raken telt niet
        self.assertEqual(g.phase, "play")
        self.assertEqual(g.players[0].points, 4)

    def test_correct_invalid_index(self):
        g = setup_game(extra=True)
        self.assertFalse(g.correct(0, d("S20")))

    def test_targets_announcement(self):
        g = setup_game(("Ann", "Bob", "Cas"), (20, 14, 3), (0.05, 0.2, 0.3), extra=True)
        g.throw(d("D20")); g.throw(d("D20")); g.takeout()   # Ann 4
        g.takeout(); g.next_player(); g.next_player()        # Bob, Cas slaan over
        g.throw(d("S20"))                                    # Ann 5
        self.assertIn("Bob nummer 14 met 0 punten, Cas nummer 3 met 0 punten", g.state()["announce"])
        self.assertIn("Bob, number 14, on 0 points, Cas, number 3, on 0 points", g.state("en")["announce"])



class KnockOutRuleTests(unittest.TestCase):
    """Af ben je alleen door een ANDERE speler: die zet je op 0 (pijl of bonus), of raakt je nummer
    terwijl je al op 0 staat. Op 0 staan kan geen bonuspunten kosten; jezelf op 0 gooien kost je niets."""

    def _start(self, names=("Eloy", "Sanne")):
        g = Game()
        g.new_game(list(names))
        nums = (20, 5, 1)
        for k, _ in enumerate(names):
            g.throw({"number": nums[k], "multiplier": 1})
            g.throw({"number": 25, "multiplier": 2, "x": 0.01 * (k + 1), "y": 0})
            g.takeout()
        return g

    def test_ton_bonus_against_zero_does_not_win(self):
        g = self._start()
        g.throw({"number": 20, "multiplier": 3})
        g.throw({"number": 20, "multiplier": 2})     # 5 punten én 100+ in de eerste beurt
        self.assertEqual(g.phase, "play")
        self.assertFalse(g.players[1].out)
        self.assertEqual(g.players[1].points, 0)
        g.throw({"number": 5, "multiplier": 1})       # echte treffer op haar nummer: wel af
        self.assertEqual(g.phase, "finished")

    def test_bonus_taking_last_point_knocks_out(self):
        g = self._start()
        g.players[0].points = 5
        g.players[0].reached_target = True
        g.players[1].points = 1
        g.players[1].scored = True
        g.throw({"number": 25, "multiplier": 2})      # bullseye: Eloy zet Sanne op 0 → af
        self.assertTrue(g.players[1].out)
        self.assertEqual(g.phase, "finished")

    def test_own_miss_to_zero_is_not_out(self):
        g = self._start()
        g.players[0].points = 5
        g.players[0].reached_target = True
        g.next_player()                               # Sanne
        g.throw({"number": 5, "multiplier": 1})       # 0 → 1
        g.throw({"number": 0, "multiplier": 0, "x": 0.0, "y": 1.5})   # naast het bord: 1 → 0
        self.assertEqual(g.players[1].points, 0)
        self.assertFalse(g.players[1].out)
        self.assertEqual(g.phase, "play")
        g.next_player()                               # Eloy raakt haar op 0: af
        g.throw({"number": 5, "multiplier": 1})
        self.assertTrue(g.players[1].out)

    def test_allocation_only_to_players_with_points(self):
        g = self._start(("Eloy", "Sanne", "Mark"))
        g.players[0].points = 5
        g.players[2].points = 2
        g.throw({"number": 25, "multiplier": 1})      # bull: 1 punt, alleen Mark heeft punten → automatisch
        self.assertEqual(g.players[2].points, 1)
        self.assertIsNone(g.state()["pending"])
        g.players[1].points = 2
        g.throw({"number": 25, "multiplier": 2})      # 2 kandidaten: kiezen
        self.assertEqual(sorted(g.state()["pending"]["targets"]), [1, 2])
        g.allocate([[1, 2], [2, 1]])                  # beiden op 0 gezet door Eloy: af
        self.assertTrue(g.players[1].out and g.players[2].out)
        self.assertEqual(g.phase, "finished")


if __name__ == "__main__":
    unittest.main()
