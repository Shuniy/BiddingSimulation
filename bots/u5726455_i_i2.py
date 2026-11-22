import math
from collections import Counter
from statistics import mean


class Bot(object):
    def __init__(self):
        self.name = "Budget Reserve Bidder"

        self.artists = ["Da Vinci", "Picasso", "Rembrandt", "Van Gogh"]

        # Narrow regret memory: only updated on narrow misses / overpriced unnecessary wins
        self.regret = {artist: 0 for artist in self.artists}
        self.last_round = -1
        self.last_painting = None
        self.last_bid = 0
        self.last_needed = False

    # =========================
    # Main API
    # =========================
    def get_bid(
        self,
        current_round,
        bots,
        winner_pays,
        artists_and_values,
        round_limit,
        starting_budget,
        painting_order,
        target_collection,
        my_bot_details,
        current_painting,
        winner_ids,
        amounts_paid,
    ):
        state = self.build_state(
            current_round=current_round,
            bots=bots,
            round_limit=round_limit,
            starting_budget=starting_budget,
            painting_order=painting_order,
            current_painting=current_painting,
            winner_ids=winner_ids,
            amounts_paid=amounts_paid,
            my_bot_details=my_bot_details,
        )

        my_budget = state["my_budget"]
        if my_budget <= 0:
            self._store_last_round_info(current_round, current_painting, 0, False)
            return 0

        self.update_regret(state)
        features = self.extract_features(state)
        bid, needed = self.decide_bid(state, features)

        bid = int(max(0, min(my_budget, bid)))
        self._store_last_round_info(current_round, current_painting, bid, needed)
        return bid

    # =========================
    # State building
    # =========================
    def build_state(
        self,
        current_round,
        bots,
        round_limit,
        starting_budget,
        painting_order,
        current_painting,
        winner_ids,
        amounts_paid,
        my_bot_details,
    ):
        normalized_bots = [self.normalize_bot(bot) for bot in bots]
        my_bot = self.normalize_bot(my_bot_details)

        return {
            "current_round": int(current_round),
            "round_limit": int(round_limit),
            "remaining_rounds": max(1, int(round_limit) - int(current_round)),
            "progress": int(current_round) / max(1, int(round_limit)),
            "starting_budget": int(starting_budget),
            "painting_order": list(painting_order),
            "current_painting": str(current_painting),
            "winner_ids": list(winner_ids),
            "amounts_paid": list(amounts_paid),
            "my_bot": my_bot,
            "my_id": my_bot["bot_unique_id"],
            "my_budget": my_bot["budget"],
            "my_score": my_bot["score"],
            "my_paintings": my_bot["paintings"],
            "opponents": [
                bot
                for bot in normalized_bots
                if bot["bot_unique_id"] != my_bot["bot_unique_id"]
            ],
            "room_size": len(normalized_bots),
        }

    def normalize_bot(self, bot):
        return {
            "bot_name": bot["bot_name"],
            "bot_unique_id": bot["bot_unique_id"],
            "paintings": self.normalize_paintings(bot["paintings"]),
            "budget": int(bot["budget"]),
            "score": int(bot["score"]),
        }

    def normalize_paintings(self, paintings):
        return {artist: int(paintings.get(artist, 0)) for artist in self.artists}

    # =========================
    # Regret memory
    # =========================
    def update_regret(self, state):
        current_round = state["current_round"]
        winner_ids = state["winner_ids"]
        amounts_paid = state["amounts_paid"]
        my_id = state["my_id"]

        if (
            current_round == 0
            or self.last_painting is None
            or self.last_round != current_round - 1
            or len(winner_ids) < current_round
            or len(amounts_paid) < current_round
        ):
            return

        winner = winner_ids[-1]
        amount_paid = int(amounts_paid[-1])

        # Narrow miss on a needed category -> regret up
        if (
            self.last_needed
            and self.last_bid > 0
            and winner != my_id
            and amount_paid <= self.last_bid + 2
        ):
            self.regret[self.last_painting] = min(
                self.regret[self.last_painting] + 1, 4
            )

        # Overpriced win on non-needed category -> regret down
        elif (not self.last_needed) and winner == my_id and amount_paid >= 12:
            self.regret[self.last_painting] = max(
                self.regret[self.last_painting] - 1, 0
            )

    def _store_last_round_info(self, current_round, current_painting, bid, needed):
        self.last_round = current_round
        self.last_painting = current_painting
        self.last_bid = bid
        self.last_needed = needed

    # =========================
    # Feature extraction
    # =========================
    def extract_features(self, state):
        current_painting = state["current_painting"]
        my_paintings = state["my_paintings"]
        painting_order = state["painting_order"]
        current_round = state["current_round"]
        amounts_paid = state["amounts_paid"]

        remaining_supply = self.get_remaining_supply(painting_order, current_round)
        future_window_supply = self.get_future_window_supply(
            painting_order, current_round, [8, 20, 50]
        )

        current_score = self.product_score(my_paintings)
        marginal_gain = self.marginal_product_gain(my_paintings, current_painting)
        market_price = self.estimate_market_price(
            current_painting, painting_order, amounts_paid
        )

        opponent_model = self.model_opponents(state, market_price)

        scarcity_score = self.compute_scarcity_score(
            current_painting, remaining_supply, future_window_supply
        )
        long_horizon_scarcity = self.compute_long_horizon_scarcity(
            remaining_rounds=state["remaining_rounds"],
            remaining_current=max(1, remaining_supply[current_painting]),
        )

        min_count = min(my_paintings.values())
        current_count = my_paintings[current_painting]
        lead = current_count - min_count
        balance_pressure = self.compute_balance_pressure(my_paintings, current_painting)

        endgame_state = self.compute_endgame_state(state, remaining_supply)
        pace = state["my_budget"] / max(1, state["remaining_rounds"])

        return {
            "remaining_supply": remaining_supply,
            "future_window_supply": future_window_supply,
            "current_score": current_score,
            "marginal_gain": marginal_gain,
            "market_price": market_price,
            "opponent_model": opponent_model,
            "scarcity_score": scarcity_score,
            "long_horizon_scarcity": long_horizon_scarcity,
            "lead": lead,
            "min_count": min_count,
            "current_count": current_count,
            "balance_pressure": balance_pressure,
            "regret": self.regret.get(current_painting, 0),
            "endgame_state": endgame_state,
            "pace": pace,
        }

    # =========================
    # Basic utilities
    # =========================
    def product_score(self, paintings):
        score = 1
        for artist in self.artists:
            score *= max(0, int(paintings.get(artist, 0)))
        return score

    def marginal_product_gain(self, my_paintings, current_painting):
        old_score = self.product_score(my_paintings)
        new_paintings = dict(my_paintings)
        new_paintings[current_painting] += 1
        new_score = self.product_score(new_paintings)
        return new_score - old_score

    def get_remaining_supply(self, painting_order, current_round):
        counts = {artist: 0 for artist in self.artists}
        for artist in painting_order[current_round:]:
            if artist in counts:
                counts[artist] += 1
        return counts

    def get_future_window_supply(self, painting_order, current_round, window_sizes):
        result = {}
        for window in window_sizes:
            counts = {artist: 0 for artist in self.artists}
            for artist in painting_order[current_round : current_round + window]:
                if artist in counts:
                    counts[artist] += 1
            result[window] = counts
        return result

    def robust_median(self, values):
        if not values:
            return 1
        vals = sorted(int(v) for v in values)
        if len(vals) <= 2:
            return vals[len(vals) // 2]
        trim = int(len(vals) * 0.15)
        trimmed = vals[trim : len(vals) - trim] if len(vals) - 2 * trim >= 1 else vals
        return trimmed[len(trimmed) // 2]

    def estimate_market_price(self, current_painting, painting_order, amounts_paid):
        if not amounts_paid:
            return 1

        history_types = painting_order[: len(amounts_paid)]
        type_prices = [
            price
            for price, artist in zip(amounts_paid, history_types)
            if artist == current_painting
        ]
        recent_all = amounts_paid[-10:] if len(amounts_paid) >= 10 else amounts_paid

        if not type_prices:
            return max(1, int(self.robust_median(recent_all)))

        recent_type_prices = type_prices[-6:] if len(type_prices) >= 6 else type_prices
        type_estimate = self.robust_median(recent_type_prices)
        all_estimate = self.robust_median(recent_all)

        return max(1, int(0.7 * type_estimate + 0.3 * all_estimate))

    def compute_scarcity_score(
        self, current_painting, remaining_supply, future_window_supply
    ):
        total_remaining = remaining_supply[current_painting]
        near_8 = future_window_supply[8][current_painting]
        near_20 = future_window_supply[20][current_painting]

        if total_remaining <= 0:
            return 1.0

        overall_scarcity = 1.0 / total_remaining
        local_urgency = 0.0

        if near_8 == 0:
            local_urgency += 0.45
        elif near_8 == 1:
            local_urgency += 0.20

        if near_20 <= 1:
            local_urgency += 0.25
        elif near_20 <= 3:
            local_urgency += 0.10

        return min(1.0, overall_scarcity * 6.0 + local_urgency)

    def compute_long_horizon_scarcity(self, remaining_rounds, remaining_current):
        # Higher means scarcer relative to time left
        return remaining_rounds / max(1, remaining_current)

    def compute_balance_pressure(self, my_paintings, current_painting):
        current_count = my_paintings[current_painting]
        min_count = min(my_paintings.values())

        if current_count == min_count:
            return 1.0
        elif current_count == min_count + 1:
            return 0.6
        elif current_count == min_count + 2:
            return 0.3
        return 0.1

    # =========================
    # Opponent modelling
    # =========================
    def build_opponent_history(self, state):
        winner_ids = state["winner_ids"]
        amounts_paid = state["amounts_paid"]
        painting_order = state["painting_order"]
        history_len = min(len(winner_ids), len(amounts_paid), len(painting_order))

        history = {}
        for opp in state["opponents"]:
            history[opp["bot_unique_id"]] = {
                "total_wins": 0,
                "wins_by_artist": {artist: 0 for artist in self.artists},
                "prices_by_artist": {artist: [] for artist in self.artists},
                "recent_wins_by_artist": {artist: 0 for artist in self.artists},
            }

        recent_window = 20
        recent_start = max(0, history_len - recent_window)

        for i in range(history_len):
            winner_id = winner_ids[i]
            artist = painting_order[i]
            paid = int(amounts_paid[i])

            if winner_id not in history:
                history[winner_id] = {
                    "total_wins": 0,
                    "wins_by_artist": {a: 0 for a in self.artists},
                    "prices_by_artist": {a: [] for a in self.artists},
                    "recent_wins_by_artist": {a: 0 for a in self.artists},
                }

            if artist in self.artists:
                history[winner_id]["total_wins"] += 1
                history[winner_id]["wins_by_artist"][artist] += 1
                history[winner_id]["prices_by_artist"][artist].append(paid)
                if i >= recent_start:
                    history[winner_id]["recent_wins_by_artist"][artist] += 1

        return history

    def compute_opponent_need(
        self, opponent_paintings, current_painting, my_current_count
    ):
        opp_count = opponent_paintings[current_painting]
        base_need = 1.0 / (opp_count + 1)
        if opp_count < my_current_count:
            base_need += 0.15
        return min(1.0, base_need)

    def compute_budget_strength(self, opponent_budget, starting_budget):
        return min(1.0, opponent_budget / max(1, starting_budget))

    def compute_score_pressure(self, opponent_score, my_score):
        if opponent_score < my_score:
            gap_ratio = (my_score - opponent_score) / max(1, my_score)
            return min(1.0, 0.4 + gap_ratio)
        return 0.4

    def compute_artist_aggression(
        self, opp_history, current_painting, total_rounds_played
    ):
        if not opp_history or total_rounds_played <= 0:
            return 0.0

        total_wins = opp_history["total_wins"]
        wins_for_artist = opp_history["wins_by_artist"][current_painting]
        recent_wins_for_artist = opp_history["recent_wins_by_artist"][current_painting]

        overall_win_rate = total_wins / max(1, total_rounds_played)
        artist_focus = wins_for_artist / max(1, total_wins)
        recent_focus = recent_wins_for_artist / 20.0

        aggression = 0.30 * overall_win_rate + 0.45 * artist_focus + 0.25 * recent_focus
        return min(1.0, aggression)

    def compute_price_aggression(self, opp_history, current_painting, market_price):
        if not opp_history:
            return 0.0

        prices = opp_history["prices_by_artist"][current_painting]
        if not prices or market_price <= 0:
            return 0.0

        avg_price = sum(prices) / len(prices)
        ratio = avg_price / market_price
        return min(1.0, ratio / 2.0)

    def model_opponents(self, state, market_price):
        current_painting = state["current_painting"]
        opponents = state["opponents"]
        starting_budget = state["starting_budget"]
        my_score = state["my_score"]
        my_paintings = state["my_paintings"]
        amounts_paid = state["amounts_paid"]

        my_current_count = my_paintings[current_painting]
        total_rounds_played = len(amounts_paid)
        opponent_history = self.build_opponent_history(state)

        profiles = []
        threats = []

        for opp in opponents:
            opp_id = opp["bot_unique_id"]
            opp_hist = opponent_history.get(opp_id)

            opp_need = self.compute_opponent_need(
                opp["paintings"], current_painting, my_current_count
            )
            budget_strength = self.compute_budget_strength(
                opp["budget"], starting_budget
            )
            score_pressure = self.compute_score_pressure(opp["score"], my_score)
            artist_aggression = self.compute_artist_aggression(
                opp_hist, current_painting, total_rounds_played
            )
            price_aggression = self.compute_price_aggression(
                opp_hist, current_painting, market_price
            )

            threat = min(
                1.0,
                0.30 * opp_need
                + 0.25 * budget_strength
                + 0.15 * score_pressure
                + 0.20 * artist_aggression
                + 0.10 * price_aggression,
            )

            profiles.append(
                {
                    "bot_name": opp["bot_name"],
                    "bot_unique_id": opp["bot_unique_id"],
                    "threat": threat,
                    "opp_need": opp_need,
                    "budget_strength": budget_strength,
                    "artist_aggression": artist_aggression,
                    "price_aggression": price_aggression,
                }
            )
            threats.append(threat)

        if threats:
            strongest = max(threats)
            average = sum(threats) / len(threats)
            total_pressure = 0.65 * strongest + 0.35 * average
        else:
            strongest = 0.0
            average = 0.0
            total_pressure = 0.0

        return {
            "profiles": profiles,
            "strongest_threat": strongest,
            "average_threat": average,
            "total_pressure": total_pressure,
        }

    # =========================
    # Room overlays
    # =========================
    def summarise_small_room(self, state):
        bots = [state["my_bot"]] + state["opponents"]
        my_id = state["my_id"]
        current_painting = state["current_painting"]
        current_round = state["current_round"]
        starting_budget = state["starting_budget"]
        remaining_rounds = state["remaining_rounds"]

        market_pressure = []
        flat_floor = 0
        volatile_exists = False

        for bot in bots:
            if bot["bot_unique_id"] == my_id:
                continue

            wins = sum(bot["paintings"].values())
            avg_price = (starting_budget - bot["budget"]) / max(1, wins)
            opponent_min = min(bot["paintings"].values())
            needs_current = bot["paintings"][current_painting] == opponent_min

            if wins >= 3 and avg_price >= 15 and current_round < 80:
                volatile_exists = True

            if not needs_current:
                continue

            if wins >= 5 and 8 <= avg_price <= 12:
                flat_floor = 10

            market_pressure.append(bot["budget"] / max(1, remaining_rounds))

        market = mean(market_pressure) if market_pressure else 0.0
        return {
            "market": market,
            "flat_floor": flat_floor,
            "volatile_exists": volatile_exists,
        }

    def summarise_large_room(self, state):
        bots = [state["my_bot"]] + state["opponents"]
        my_id = state["my_id"]
        current_painting = state["current_painting"]
        current_round = state["current_round"]
        starting_budget = state["starting_budget"]
        remaining_rounds = state["remaining_rounds"]

        urgent_prices = []
        market_pressure = []
        flat_floor = 0
        volatile_exists = False

        for bot in bots:
            if bot["bot_unique_id"] == my_id:
                continue

            wins = sum(bot["paintings"].values())
            avg_price = (starting_budget - bot["budget"]) / max(1, wins)
            opponent_min = min(bot["paintings"].values())
            needs_current = bot["paintings"][current_painting] == opponent_min

            if wins >= 3 and avg_price >= 15 and current_round < 80:
                volatile_exists = True

            if wins >= 5 and 8 <= avg_price <= 12:
                flat_floor = max(flat_floor, 10)
            elif wins >= 5 and 13 <= avg_price <= 17:
                flat_floor = max(flat_floor, 15)

            if not needs_current:
                continue

            urgent_prices.append(avg_price)
            market_pressure.append(bot["budget"] / max(1, remaining_rounds))

        if not urgent_prices or max(urgent_prices) < 8:
            pressure_bin = 0
        elif max(urgent_prices) < 13:
            pressure_bin = 1
        elif max(urgent_prices) < 18:
            pressure_bin = 2
        else:
            pressure_bin = 3

        market = mean(market_pressure) if market_pressure else 0.0
        return {
            "pressure_bin": pressure_bin,
            "market": market,
            "flat_floor": flat_floor,
            "volatile_exists": volatile_exists,
        }

    # =========================
    # Endgame
    # =========================
    def compute_endgame_state(self, state, remaining_supply):
        progress = state["progress"]
        remaining_rounds = state["remaining_rounds"]
        my_budget = state["my_budget"]
        my_paintings = state["my_paintings"]
        current_painting = state["current_painting"]

        min_count = min(my_paintings.values())
        current_count = my_paintings[current_painting]
        budget_per_remaining_round = my_budget / max(1, remaining_rounds)
        supply_left = remaining_supply[current_painting]

        is_late_game = progress >= 0.65
        is_deep_endgame = progress >= 0.88 or remaining_rounds <= 15
        is_weak_category = current_count == min_count
        scarce_now = supply_left <= 5

        urgency = 0.0
        if is_late_game:
            urgency += 0.25
        if is_deep_endgame:
            urgency += 0.25
        if is_weak_category:
            urgency += 0.25
        if scarce_now:
            urgency += 0.15
        if supply_left <= 2:
            urgency += 0.10

        urgency = min(1.0, urgency)

        mode = "normal"
        if is_deep_endgame and (is_weak_category or scarce_now):
            mode = "must_convert"
        elif is_late_game:
            mode = "late_game"

        return {
            "mode": mode,
            "urgency": urgency,
            "budget_per_remaining_round": budget_per_remaining_round,
        }

    # =========================
    # Lightweight anti-predictability
    # =========================
    def deterministic_jitter(self, current_round, current_painting):
        seed = (current_round * 17 + len(current_painting) * 13) % 5
        if seed == 0:
            return -1
        elif seed == 1:
            return 1
        return 0

    def stochastic_bid_jitter(self, state, features, candidate_bid):
        market_price = features["market_price"]
        total_pressure = features["opponent_model"]["total_pressure"]
        endgame_mode = features["endgame_state"]["mode"]
        scarcity_score = features["scarcity_score"]

        jitter = self.deterministic_jitter(
            state["current_round"], state["current_painting"]
        )

        if abs(candidate_bid - market_price) <= 2 and total_pressure >= 0.35:
            jitter += 1

        if scarcity_score >= 0.5 and endgame_mode != "normal":
            jitter += 1

        return max(-1, min(2, jitter))

    # =========================
    # Bid decision
    # =========================
    def decide_bid(self, state, features):
        room_size = state["room_size"]
        if room_size <= 5:
            return self.decide_small_room_bid(state, features)
        return self.decide_large_room_bid(state, features)

    def decide_small_room_bid(self, state, features):
        my_budget = state["my_budget"]
        current_round = state["current_round"]
        remaining_rounds = state["remaining_rounds"]
        current_count = features["current_count"]
        lead = features["lead"]
        pace = features["pace"]
        market_price = features["market_price"]
        long_horizon_scarcity = features["long_horizon_scarcity"]
        local_scarcity = features["scarcity_score"]
        total_pressure = features["opponent_model"]["total_pressure"]
        regret = features["regret"]
        endgame = features["endgame_state"]
        marginal_gain = features["marginal_gain"]

        overlay = self.summarise_small_room(state)
        market = overlay["market"]
        flat_floor = overlay["flat_floor"]
        volatile_exists = overlay["volatile_exists"]

        # Keep our logic, but anchor it to pace and bottleneck need
        normalized_gain = math.log1p(max(0, marginal_gain))
        need_bonus = 1.0 if lead == 0 else (0.35 if lead == 1 else -0.25)

        raw_bid = (
            pace
            * (
                0.85
                + 0.75 * normalized_gain
                + 0.90 * need_bonus
                + 0.18 * max(0.0, long_horizon_scarcity - 1.0)
                + 0.20 * local_scarcity
                + 0.25 * total_pressure
            )
            + 0.70 * market
            + 0.55 * regret
        )

        # Stronger focus on bottleneck categories
        if current_count == 0:
            raw_bid += 1.5
        elif lead == 0:
            raw_bid += 0.8

        # Long-auction conservation
        if remaining_rounds > 100:
            raw_bid *= 0.88
        elif remaining_rounds > 60:
            raw_bid *= 0.94

        # Borrow the other bot's floor logic
        if current_count == 0:
            raw_bid = max(raw_bid, max(flat_floor, 10))
            if long_horizon_scarcity > 1.2 or current_round > 150:
                raw_bid = max(raw_bid, 11)
        elif lead == 0 and flat_floor:
            raw_bid = max(raw_bid, 10)

        # Volatile rooms: cap aggression early
        if volatile_exists and current_round < 80:
            if lead == 0:
                cap = 11 if (current_count == 0 or long_horizon_scarcity > 1.2) else 10
                raw_bid = min(raw_bid, cap)
            else:
                raw_bid = min(raw_bid * 0.45, 7)

        # Our endgame
        if endgame["mode"] == "late_game":
            raw_bid *= 1.08
        elif endgame["mode"] == "must_convert":
            raw_bid *= 1.20
            raw_bid = max(raw_bid, market_price + 2)

        # Controlled cap
        hard_cap = self.compute_hard_cap(state, features)
        candidate_bid = min(raw_bid, hard_cap)

        # Worthless item filter
        needed = lead == 0
        if not needed and local_scarcity < 0.15 and normalized_gain < 1.0:
            candidate_bid = min(candidate_bid, max(0, market_price - 1))

        candidate_bid += self.stochastic_bid_jitter(state, features, candidate_bid)
        candidate_bid = max(0, min(my_budget, candidate_bid))

        return int(math.floor(candidate_bid)), needed

    def decide_large_room_bid(self, state, features):
        my_budget = state["my_budget"]
        current_round = state["current_round"]
        remaining_rounds = state["remaining_rounds"]
        current_count = features["current_count"]
        lead = features["lead"]
        pace = features["pace"]
        market_price = features["market_price"]
        long_horizon_scarcity = features["long_horizon_scarcity"]
        local_scarcity = features["scarcity_score"]
        total_pressure = features["opponent_model"]["total_pressure"]
        regret = features["regret"]
        endgame = features["endgame_state"]
        marginal_gain = features["marginal_gain"]

        overlay = self.summarise_large_room(state)
        pressure_bin = overlay["pressure_bin"]
        market = overlay["market"]
        flat_floor = overlay["flat_floor"]
        volatile_exists = overlay["volatile_exists"]

        normalized_gain = math.log1p(max(0, marginal_gain))

        if current_count == 0:
            need_level = 0
        elif lead == 0:
            need_level = 1
        elif lead == 1:
            need_level = 2
        else:
            need_level = 3

        need_bonus = {0: 1.2, 1: 0.9, 2: 0.35, 3: -0.35}[need_level]

        raw_bid = (
            pace
            * (
                0.90
                + 0.70 * normalized_gain
                + 0.95 * need_bonus
                + 0.22 * max(0.0, long_horizon_scarcity - 1.0)
                + 0.18 * local_scarcity
                + 0.30 * total_pressure
            )
            + 0.70 * market
            + 0.80 * regret
        )

        # Long-auction conservation
        if remaining_rounds > 100:
            raw_bid *= 0.88
        elif remaining_rounds > 60:
            raw_bid *= 0.94

        # Import the large-room band logic
        if need_level in (0, 1):
            floor = 0

            if flat_floor >= 15:
                floor = 16
            elif flat_floor >= 10:
                floor = 11
            elif pressure_bin >= 2:
                floor = 16
            elif pressure_bin == 1:
                floor = 11
            elif need_level == 0:
                floor = 10

            if need_level == 0:
                floor = max(floor, 11 if pressure_bin <= 1 else 16)

            if long_horizon_scarcity > 1.3:
                floor = max(
                    floor,
                    16 if pressure_bin >= 1 or flat_floor >= 15 else 11,
                )

            if (
                state["room_size"] >= 9
                and long_horizon_scarcity > 1.45
                and need_level == 0
            ):
                floor = max(floor, 20)

            raw_bid = max(raw_bid, floor)

        elif need_level == 2:
            raw_bid = max(raw_bid, pace if pressure_bin == 0 else max(pace, 10))
            if flat_floor >= 15 and long_horizon_scarcity > 1.25:
                raw_bid = max(raw_bid, 16)

        else:
            raw_bid = min(raw_bid, max(0, pace * 0.8))

        # Volatile early rooms
        if volatile_exists and current_round < 80:
            if lead == 0:
                cap = 11 if (current_count == 0 or long_horizon_scarcity > 1.2) else 10
                if flat_floor >= 15 or pressure_bin >= 2:
                    cap = 16
                raw_bid = min(raw_bid, cap)
            else:
                raw_bid = min(raw_bid * 0.45, 7)

        # Our endgame
        if endgame["mode"] == "late_game":
            raw_bid *= 1.08
        elif endgame["mode"] == "must_convert":
            raw_bid *= 1.22
            raw_bid = max(raw_bid, market_price + 2)

        hard_cap = self.compute_hard_cap(state, features)
        candidate_bid = min(raw_bid, hard_cap)

        needed = need_level in (0, 1)
        if not needed and local_scarcity < 0.15 and normalized_gain < 1.0:
            candidate_bid = min(candidate_bid, max(0, market_price - 1))

        candidate_bid += self.stochastic_bid_jitter(state, features, candidate_bid)
        candidate_bid = max(0, min(my_budget, candidate_bid))

        return int(math.floor(candidate_bid)), needed

    def compute_hard_cap(self, state, features):
        my_budget = state["my_budget"]
        starting_budget = state["starting_budget"]
        progress = state["progress"]
        remaining_rounds = state["remaining_rounds"]
        budget_per_remaining_round = my_budget / max(1, remaining_rounds)
        endgame_mode = features["endgame_state"]["mode"]
        endgame_urgency = features["endgame_state"]["urgency"]

        # Reserve budget policy for long auctions
        reserve_budget = 0
        if remaining_rounds > 100:
            reserve_budget = int(starting_budget * 0.35)
        elif remaining_rounds > 60:
            reserve_budget = int(starting_budget * 0.20)
        elif remaining_rounds > 30:
            reserve_budget = int(starting_budget * 0.10)

        spendable_budget = max(0, my_budget - reserve_budget)

        if progress < 0.33:
            phase_cap = max(8, int(my_budget * 0.05))
        elif progress < 0.65:
            phase_cap = max(10, int(my_budget * 0.09))
        elif progress < 0.85:
            phase_cap = max(16, int(my_budget * 0.18))
        else:
            phase_cap = max(24, int(my_budget * 0.35))

        if progress < 0.65:
            pacing_cap = max(6, int(budget_per_remaining_round * 1.2))
        elif progress < 0.85:
            pacing_cap = max(10, int(budget_per_remaining_round * 1.8))
        else:
            pacing_cap = max(16, int(budget_per_remaining_round * 3.0))

        hard_cap = min(max(0, spendable_budget), max(phase_cap, pacing_cap))

        if endgame_mode == "late_game" and endgame_urgency >= 0.5:
            hard_cap = min(
                my_budget, max(hard_cap, int(budget_per_remaining_round * 2.5))
            )

        if endgame_mode == "must_convert":
            hard_cap = min(
                my_budget, max(hard_cap, int(budget_per_remaining_round * 4.0))
            )

        return max(0, hard_cap)
