import unittest

from wss import FoodBonus, GameMap, Mountain, PatientTrader, Plains, Position, Resources, Square, WaterBonus, make_game


def sq(terrain=Plains, items=()):
    return Square(terrain(), list(items))


def game_map(rows):
    return GameMap(len(rows[0]), len(rows), rows)


class WSSTest(unittest.TestCase):
    def test_resources_cap_and_payment(self) -> None:
        r = Resources(strength=5, water=4, food=3, gold=2)
        self.assertTrue(r.can_pay(Resources(strength=4, water=1)))
        self.assertFalse(r.can_pay(Resources(gold=3)))
        self.assertEqual((r + Resources(water=10)).capped(r).water, 4)

    def test_manual_backend_has_no_turn_runner(self) -> None:
        game = make_game(seed=3560)
        self.assertFalse(hasattr(game, "step"))
        self.assertFalse(hasattr(game, "run"))

    def test_start_initializes_once_and_collects_start_square_once(self) -> None:
        game = make_game(width=3, height=1, seed=7)
        game.player.maximums = Resources(strength=10, water=10, food=10)
        game.player.resources = Resources(strength=10, water=10, food=5)
        game.map = game_map([[sq(items=[FoodBonus(5)]), sq(), sq()]])
        first, second = game.start(), game.start()
        self.assertEqual(first.resources.food, 10)
        self.assertEqual(second.resources.food, 10)
        self.assertEqual(sum("collected food bonus" in line for line in game.log), 1)

    def test_manual_move_uses_costs_and_updates_snapshot(self) -> None:
        game = make_game(width=3, height=1, seed=7)
        game.map = game_map([[sq(), sq(), sq()]])
        start = game.start()
        result = game.manual_move((1, 0))
        self.assertEqual(game.turn, 1)
        self.assertEqual(result.snapshot.position, Position(1, 0))
        self.assertEqual(result.snapshot.resources, start.resources - Plains.cost)
        with self.assertRaises(ValueError):
            game.manual_move((1, 1))

    def test_blocked_or_unaffordable_move_does_not_spend_turn(self) -> None:
        game = make_game(width=2, height=1, seed=7)
        game.map = game_map([[sq(), sq(Mountain)]])
        game.player.resources = Resources(strength=2, water=1, food=1, gold=0)
        start = game.start()
        blocked = game.manual_move((-1, 0))
        unaffordable = game.manual_move((1, 0))
        self.assertEqual(game.turn, 0)
        self.assertEqual(blocked.snapshot.resources, start.resources)
        self.assertEqual(unaffordable.snapshot.resources, start.resources)
        self.assertIn("blocked", blocked.messages[0])
        self.assertIn("cannot enter", unaffordable.messages[0])

    def test_affordable_moves_are_cardinal_only(self) -> None:
        game = make_game(width=3, height=3, seed=7)
        game.map = game_map([[sq() for _ in range(3)] for _ in range(3)])
        game.player.position = Position(1, 1)
        snapshot = game.start()
        self.assertEqual(set(snapshot.affordable_moves), {Position(1, 0), Position(1, 2), Position(0, 1), Position(2, 1)})

    def test_repeating_bonus_collects_again_on_later_turn(self) -> None:
        game = make_game(width=3, height=1, seed=7)
        game.player.maximums = Resources(strength=20, water=20, food=20)
        game.player.resources = Resources(strength=10, water=5, food=10)
        game.map = game_map([[sq(items=[WaterBonus(5, repeating=True), FoodBonus(5)]), sq(), sq()]])
        game.start()
        self.assertEqual(game.player.resources.water, 10)
        self.assertEqual(game.player.resources.food, 15)
        game.manual_move((1, 0))
        game.manual_move((-1, 0))
        self.assertEqual(game.player.resources.water, 13)
        self.assertEqual(game.player.resources.food, 13)
        self.assertEqual(sum("collected food bonus" in line for line in game.log), 1)
        self.assertEqual(sum("collected water bonus" in line for line in game.log), 2)

    def test_manual_trader_interaction_adjacent(self) -> None:
        game = make_game(width=3, height=1, seed=7)
        game.player.maximums = Resources(strength=10, water=20, food=20, gold=5)
        game.player.resources = Resources(strength=10, water=5, food=9, gold=3)
        game.map = game_map([[sq(), sq(items=[PatientTrader()]), sq()]])
        game.start()
        result = game.interact_trader()
        self.assertIn("trade complete", "\n".join(result.messages))
        self.assertEqual(game.player.resources.water, 13)
        self.assertEqual(game.player.resources.gold, 1)

    def test_terminal_state_is_stable_after_escape(self) -> None:
        game = make_game(width=2, height=1, seed=7)
        game.map = game_map([[sq(), sq()]])
        game.start()
        final = game.manual_move((1, 0))
        final_log_length = len(game.log)
        stable = game.manual_move((-1, 0))
        self.assertTrue(final.snapshot.finished)
        self.assertEqual(stable.messages, ())
        self.assertEqual(len(game.log), final_log_length)

    def test_map_render_marks_player_and_items(self) -> None:
        game = make_game(width=5, height=3, seed=7)
        game.player.position = Position(2, 1)
        game.map = game_map([[sq() for _ in range(5)], [sq(), sq(items=[FoodBonus(5)]), sq(), sq(items=[WaterBonus(5)]), sq()], [sq() for _ in range(5)]])
        rendered = "\n".join(game.map.render(game.player))
        self.assertIn("@", rendered)
        self.assertIn("f@w", rendered)

    def test_audio_assets_are_all_wired(self) -> None:
        from gui_app import ALL_AUDIO, ASSETS, SOUND
        mp3_files = {path.name for path in ASSETS.glob("*.mp3")}
        self.assertEqual(mp3_files, ALL_AUDIO)
        self.assertEqual(set(SOUND), {"welcome", "level", "move", "trade", "win", "lose"})
        self.assertTrue(all((ASSETS / filename).exists() for filename in SOUND.values()))


    def test_trade_assets_are_all_wired(self) -> None:
        from gui_app import ASSETS, DIALOG, SCENE, SOUND, TRADE_ASSETS
        trade_files = {
            path.name for path in ASSETS.glob("*")
            if any(word in path.name for word in ("trade", "trader", "dialog")) or path.name == "no_trader_available.png"
        }
        wired = set(DIALOG.values()) | set(SCENE.values()) | {SOUND["trade"]} | TRADE_ASSETS
        self.assertEqual(trade_files, TRADE_ASSETS)
        self.assertTrue(trade_files <= wired)
        self.assertTrue(all((ASSETS / filename).exists() for filename in trade_files))



    def test_app_and_no_trader_assets_exist(self) -> None:
        from gui_app import ALL_PNG, ASSETS
        self.assertIn("app_icon.png", ALL_PNG)
        self.assertIn("no_trader_available.png", ALL_PNG)
        self.assertTrue((ASSETS / "app_icon.png").exists())
        self.assertTrue((ASSETS / "no_trader_available.png").exists())



if __name__ == "__main__":
    unittest.main()
