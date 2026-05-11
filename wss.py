from collections import namedtuple
from random import Random

RESOURCE_FIELDS = ("strength", "water", "food", "gold")


class Resources(namedtuple("Resources", RESOURCE_FIELDS, defaults=(0, 0, 0, 0))):
    __slots__ = ()

    def __add__(self, other: "Resources") -> "Resources":
        return Resources(*(getattr(self, name) + getattr(other, name) for name in RESOURCE_FIELDS))

    def __sub__(self, other: "Resources") -> "Resources":
        return Resources(*(getattr(self, name) - getattr(other, name) for name in RESOURCE_FIELDS))

    def can_pay(self, cost: "Resources") -> bool:
        return all(getattr(self, name) >= getattr(cost, name) for name in RESOURCE_FIELDS)

    def capped(self, cap: "Resources") -> "Resources":
        return Resources(*(min(getattr(self, name), getattr(cap, name)) for name in RESOURCE_FIELDS))

    def describe(self) -> str:
        parts = [f"{value} {name}" for name in RESOURCE_FIELDS if (value := getattr(self, name))]
        return ", ".join(parts) if parts else "nothing"


class Position(namedtuple("Position", "x y")):
    __slots__ = ()

    def moved(self, delta: tuple[int, int]) -> "Position":
        return Position(self.x + delta[0], self.y + delta[1])


MOVE_NAME = {(0, -1): "north", (0, 1): "south", (-1, 0): "west", (1, 0): "east"}
MOVE_DELTAS = tuple(MOVE_NAME)
SquareSnapshot = namedtuple("SquareSnapshot", "position terrain cost items")
GameSnapshot = namedtuple("GameSnapshot", "width height position resources maximums affordable_moves tiles finished")
TurnResult = namedtuple("TurnResult", "snapshot messages")


class Terrain:
    name = "terrain"
    symbol = "?"
    cost = Resources()


class Plains(Terrain):
    name, symbol, cost = "plains", ".", Resources(strength=1, water=1, food=1)


class Forest(Terrain):
    name, symbol, cost = "forest", "F", Resources(strength=2, water=1, food=1)


class Mountain(Terrain):
    name, symbol, cost = "mountain", "M", Resources(strength=3, water=2, food=2)


class Swamp(Terrain):
    name, symbol, cost = "swamp", "S", Resources(strength=3, water=1, food=3)


class Desert(Terrain):
    name, symbol, cost = "desert", "D", Resources(strength=1, water=4, food=3)


class BonusItem:
    kind = "bonus"

    def __init__(self, name: str, amount: Resources, repeating: bool = False) -> None:
        self.name = name
        self.amount = amount
        self.repeating = repeating
        self.taken = False
        self.last_turn_taken = -1

    def collect(self, player: "Player", game: "WSSGame") -> None:
        if (self.taken and not self.repeating) or (self.repeating and self.last_turn_taken == game.turn):
            return
        player.receive(self.amount)
        self.taken = True
        self.last_turn_taken = game.turn
        game.log.append(f"  collected {self.name}: +{self.amount.describe()} -> {player.resources.describe()}")


class FoodBonus(BonusItem):
    kind = "food"

    def __init__(self, amount: int, repeating: bool = False) -> None:
        super().__init__("food bonus", Resources(food=amount), repeating)


class WaterBonus(BonusItem):
    kind = "water"

    def __init__(self, amount: int, repeating: bool = False) -> None:
        super().__init__("water bonus", Resources(water=amount), repeating)


class GoldBonus(BonusItem):
    kind = "gold"

    def __init__(self, amount: int) -> None:
        super().__init__("gold bonus", Resources(gold=amount))


class TradeOffer(namedtuple("TradeOffer", "give take")):
    __slots__ = ()

    def describe(self) -> str:
        return f"give {self.give.describe()} for {self.take.describe()}"


ACCEPT, COUNTER, REJECT, ANGRY_QUIT = "accept", "counter", "reject", "angry quit"


class Trader:
    kind = "trader"
    def collect(self, player: "Player", game: "WSSGame") -> None:
        return None

    def interact(self, player: "Player", game: "WSSGame", offer: TradeOffer | None) -> None:
        if offer is None:
            return
        game.log.append(f"  trader encounter: player offers to {offer.describe()}")
        state, counteroffer, reason = self.evaluate(offer, game.rng)
        game.log.append(f"    trader response: {state} {reason}")
        if state == ACCEPT:
            self._apply_trade(player, offer, game)
            return
        if state in (REJECT, ANGRY_QUIT) or counteroffer is None:
            return
        if not player.resources.can_pay(counteroffer.give):
            game.log.append("    counter declined: not enough resources")
            return
        game.log.append(f"    counter accepted: {counteroffer.describe()}")
        self._apply_trade(player, counteroffer, game)

    def evaluate(self, offer: TradeOffer, rng: Random) -> tuple[str, TradeOffer | None, str]:
        raise NotImplementedError

    def value_for_offer(self, offer: TradeOffer) -> int:
        return offer.give.gold * 3 + offer.give.water + offer.give.food - offer.take.gold * 3 - offer.take.water - offer.take.food

    def counter(self, offer: TradeOffer) -> TradeOffer:
        extra_gold = 1 if offer.give.gold else 0
        extra_food = 0 if extra_gold else 1
        return TradeOffer(give=offer.give + Resources(food=extra_food, gold=extra_gold), take=offer.take)

    def _apply_trade(self, player: "Player", offer: TradeOffer, game: "WSSGame") -> None:
        if not player.resources.can_pay(offer.give):
            game.log.append("    trade failed: player cannot pay the offered resources")
            return
        player.resources = (player.resources - offer.give + offer.take).capped(player.maximums)
        game.log.append(f"    trade complete -> {player.resources.describe()}")


class PatientTrader(Trader):
    def evaluate(self, offer: TradeOffer, rng: Random) -> tuple[str, TradeOffer | None, str]:
        if self.value_for_offer(offer) >= -1:
            return ACCEPT, None, "fair enough"
        return COUNTER, self.counter(offer), "asks for a little more"


class HotHeadedTrader(Trader):
    def evaluate(self, offer: TradeOffer, rng: Random) -> tuple[str, TradeOffer | None, str]:
        if self.value_for_offer(offer) >= 1:
            return ACCEPT, None, "profitable now"
        return ANGRY_QUIT, None, "patience is gone"


class FlippyTrader(Trader):
    def evaluate(self, offer: TradeOffer, rng: Random) -> tuple[str, TradeOffer | None, str]:
        mood = rng.choice((-2, -1, 0, 1, 2))
        score = self.value_for_offer(offer) + mood
        reason = f"mood shifted to {mood:+d}"
        if score >= 1:
            return ACCEPT, None, reason
        if score <= -4:
            return REJECT, None, reason
        return COUNTER, self.counter(offer), reason


class Square(namedtuple("Square", "terrain items")):
    __slots__ = ()

    def has_kind(self, kind: str) -> bool:
        return any(item.kind == kind for item in self.items)


class GameMap(namedtuple("GameMap", "width height grid")):
    __slots__ = ()

    def contains(self, pos: Position) -> bool:
        return 0 <= pos.x < self.width and 0 <= pos.y < self.height

    def square(self, pos: Position) -> Square:
        return self.grid[pos.y][pos.x]

    def render(self, player: "Player | None" = None, trail: set[Position] | None = None) -> list[str]:
        trail = trail or set()
        lines = ["map: @ player, * route, T trader, f/w/g bonus, . plains, F forest, M mountain, S swamp, D desert"]
        for y, row in enumerate(self.grid):
            def mark(x: int, square: Square) -> str:
                pos = Position(x, y)
                if player and player.position == pos:
                    return "@"
                if pos in trail:
                    return "*"
                if square.has_kind("trader"):
                    return "T"
                if square.has_kind("food"):
                    return "f"
                if square.has_kind("water"):
                    return "w"
                if square.has_kind("gold"):
                    return "g"
                return square.terrain.symbol

            lines.append("  " + "".join(mark(x, square) for x, square in enumerate(row)))
        return lines


class DifficultyStrategy:
    weights = ((Plains, 1),)
    start = Resources(strength=100, water=100, food=100)

    def choose_terrain(self, rng: Random) -> Terrain:
        roll = rng.randint(1, sum(weight for _, weight in self.weights))
        for terrain_type, weight in self.weights:
            roll -= weight
            if roll <= 0:
                return terrain_type()
        raise AssertionError("terrain weights must not be empty")


class EasyDifficulty(DifficultyStrategy):
    name, weights, start = "easy", ((Plains, 50), (Forest, 28), (Mountain, 10), (Swamp, 6), (Desert, 6)), Resources(strength=140, water=140, food=140)


class NormalDifficulty(DifficultyStrategy):
    name, weights, start = "normal", ((Plains, 26), (Forest, 18), (Mountain, 22), (Swamp, 17), (Desert, 17)), Resources(strength=100, water=100, food=100)


class HardDifficulty(DifficultyStrategy):
    name, weights, start = "hard", ((Plains, 8), (Forest, 10), (Mountain, 24), (Swamp, 30), (Desert, 28)), Resources(strength=72, water=72, food=72)


DIFFICULTIES = dict(easy=EasyDifficulty, normal=NormalDifficulty, hard=HardDifficulty)
PROFILES = dict(
    allrounder=Resources(strength=110, water=110, food=110, gold=50),
    scout=Resources(strength=150, water=80, food=80, gold=50),
    survivalist=Resources(strength=85, water=150, food=150, gold=35),
    hoarder=Resources(strength=65, water=105, food=105, gold=150),
)


class Player:
    def __init__(self, profile: str, maximums: Resources, resources: Resources, position: Position) -> None:
        self.profile = profile
        self.maximums = maximums
        self.resources = resources
        self.position = position

    def pay(self, cost: Resources) -> bool:
        if not self.resources.can_pay(cost):
            return False
        self.resources -= cost
        return True

    def receive(self, amount: Resources) -> None:
        self.resources = (self.resources + amount).capped(self.maximums)

    def alive(self) -> bool:
        return self.resources.strength > 0 and self.resources.water > 0 and self.resources.food > 0


class WSSGame:
    def __init__(self, game_map: GameMap, player: Player, rng: Random, max_turns: int = 80) -> None:
        self.map = game_map
        self.player = player
        self.rng = rng
        self.max_turns = max_turns
        self.turn = 0
        self.trail: list[Position] = []
        self.log: list[str] = []
        self.started = False
        self.finished = False

    def start(self) -> GameSnapshot:
        if self.started:
            return self.snapshot()
        self.started = True
        self.finished = False
        self.turn = 0
        self.trail = [self.player.position]
        self.log = [
            f"WSS run: {self.map.width}x{self.map.height}, {self.player.profile}, manual mode",
            f"start at {self.player.position} with {self.player.resources.describe()}",
            *self.map.render(self.player),
        ]
        self._collect_here()
        return self.snapshot()

    def manual_move(self, delta: tuple[int, int]) -> TurnResult:
        if delta not in MOVE_NAME:
            raise ValueError(f"manual move must be one of {tuple(MOVE_NAME)}")
        if not self.started:
            self.start()
        if self.finished:
            return TurnResult(self.snapshot(), ())
        before = len(self.log)
        target = self.player.position.moved(delta)
        if not self.map.contains(target):
            self.log.append("blocked by map edge")
            return TurnResult(self.snapshot(), tuple(self.log[before:]))
        square = self.map.square(target)
        if not self.player.resources.can_pay(square.terrain.cost):
            self.log.append(f"cannot enter {square.terrain.name}: need {square.terrain.cost.describe()}")
            return TurnResult(self.snapshot(), tuple(self.log[before:]))
        self.turn += 1
        self.player.pay(square.terrain.cost)
        self.player.position = target
        self.trail.append(target)
        self.log.append(f"turn {self.turn:02d}: move {MOVE_NAME[delta]} into {square.terrain.name}; paid {square.terrain.cost.describe()} -> {self.player.resources.describe()}")
        self._collect_here()
        self._finish_if_needed()
        return TurnResult(self.snapshot(), tuple(self.log[before:]))

    def interact_trader(self, offer: "TradeOffer | None" = None) -> TurnResult:
        if not self.started:
            self.start()
        if self.finished:
            return TurnResult(self.snapshot(), ())
        before = len(self.log)
        trader = self._nearby_trader()
        if offer is None:
            offer = self._manual_offer()
        if trader and offer:
            trader.interact(self.player, self, offer)
        else:
            self.log.append("  no useful trader interaction available")
        return TurnResult(self.snapshot(), tuple(self.log[before:]))

    def snapshot(self) -> GameSnapshot:
        return GameSnapshot(
            self.map.width,
            self.map.height,
            self.player.position,
            self.player.resources,
            self.player.maximums,
            self._affordable_moves(),
            self._tile_snapshots(),
            self.finished,
        )

    def _finish(self, message: str) -> None:
        if self.finished:
            return
        self.finished = True
        self.log.extend(["route taken:", *self.map.render(self.player, set(self.trail)), message])

    def _finish_if_needed(self) -> None:
        if self.player.position.x == self.map.width - 1:
            self._finish(f"escaped on turn {self.turn} at {self.player.position}")
        elif not self.player.alive():
            self._finish(f"stopped: resource failure at {self.player.position}")
        elif self.turn >= self.max_turns:
            self._finish(f"stopped: turn limit at {self.player.position}")

    def _collect_here(self) -> None:
        for item in self.map.square(self.player.position).items:
            item.collect(self.player, self)

    def _nearby_trader(self):
        positions = (self.player.position, *(self.player.position.moved(delta) for delta in MOVE_DELTAS))
        return next((item for pos in positions if self.map.contains(pos) for item in self.map.square(pos).items if isinstance(item, Trader)), None)

    def _manual_offer(self) -> TradeOffer | None:
        if self.player.resources.gold <= 0:
            return None
        need = min(("water", "food"), key=lambda name: getattr(self.player.resources, name) / max(1, getattr(self.player.maximums, name)))
        if getattr(self.player.resources, need) >= getattr(self.player.maximums, need):
            return None
        return TradeOffer(Resources(gold=1), Resources(**{need: 8}))

    def _affordable_moves(self) -> tuple[Position, ...]:
        return tuple(
            pos
            for delta in MOVE_DELTAS
            if self.map.contains(pos := self.player.position.moved(delta)) and self.player.resources.can_pay(self.map.square(pos).terrain.cost)
        )

    def _tile_snapshots(self) -> tuple[tuple[SquareSnapshot, ...], ...]:
        return tuple(
            tuple(SquareSnapshot((pos := Position(x, y)), square.terrain.name, square.terrain.cost, self._item_names(square)) for x, square in enumerate(row))
            for y, row in enumerate(self.map.grid)
        )

    def _item_names(self, square: Square) -> tuple[str, ...]:
        return tuple(
            "Trader" if isinstance(item, Trader)
            else f"{item.name}{' (repeating)' if item.repeating else ''}" if isinstance(item, BonusItem)
            else item.kind
            for item in square.items
        )


def make_game(width: int = 12, height: int = 7, difficulty: str = "normal", profile: str = "scout", seed: int = 3560) -> WSSGame:
    rng = Random(seed)
    strategy = DIFFICULTIES[difficulty]()

    def bonus() -> BonusItem:
        choice = rng.choice(("food", "water", "gold"))
        if choice == "food":
            return FoodBonus(rng.randint(6, 14), repeating=rng.random() < 0.12)
        if choice == "water":
            return WaterBonus(rng.randint(6, 14), repeating=rng.random() < 0.18)
        return GoldBonus(rng.randint(1, 5))

    def items_for(x: int) -> list[object]:
        items: list[object] = []
        if x and rng.random() < 0.22:
            items.append(bonus())
        if 1 < x < width - 2 and rng.random() < 0.07:
            items.append(rng.choice([PatientTrader(), HotHeadedTrader(), FlippyTrader()]))
        return items

    game_map = GameMap(
        width,
        height,
        [[Square(Plains() if x in (0, width - 1) else strategy.choose_terrain(rng), items_for(x)) for x in range(width)] for _ in range(height)],
    )
    maximums = PROFILES[profile]
    start = Position(0, height // 2)
    return WSSGame(game_map, Player(profile, maximums, strategy.start.capped(maximums), start), rng)
