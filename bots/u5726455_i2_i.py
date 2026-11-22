"""
Hybrid auction bot that keeps the adaptive `i2` pipeline and adds the strongest
long-horizon controls from `i`.

What stays from `i2`:
- state building -> learning -> feature extraction -> bid decision flow
- market-price estimation from observed clears
- opponent modelling and endgame urgency handling

What is added from `i`:
- room-aware pressure bins and early volatility detection
- explicit price floors for weak categories
- stronger pace discipline in medium/long auctions

New in `i3`:
- unique-id based self lookup, so mixed rooms are robust
- flat-bot detection from observed winner-price patterns
- anti-flat uplift that steps above 10/15 when the current artist is critical
"""

import math

from bots.u5726455_i2 import Bot as BaseBot


class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.name = "Fixed-Bid Specialist"

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
            my_unique_id=my_bot_details["bot_unique_id"],
        )

        if state["my_budget"] <= 0:
            return 0

        self.update_learning(state)
        features = self.extract_features(state)
        bid = self.decide_bid(state, features)
        return int(max(0, min(state["my_budget"], bid)))

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
        my_unique_id,
    ):
        normalized_bots = [self.normalize_bot(bot) for bot in bots]
        my_bot = self.find_my_bot_by_id(normalized_bots, my_unique_id)

        return {
            "current_round": int(current_round),
            "round_limit": int(round_limit),
            "remaining_rounds": max(0, int(round_limit) - int(current_round)),
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

    def find_my_bot_by_id(self, bots, my_unique_id):
        for bot in bots:
            if bot["bot_unique_id"] == my_unique_id:
                return bot
        return bots[0]

    def extract_features(self, state):
        features = super().extract_features(state)
        current_painting = state["current_painting"]
        my_paintings = state["my_paintings"]
        min_count = min(my_paintings.values())
        current_count = my_paintings[current_painting]

        need_level = self.compute_need_level(current_count, min_count)
        room_profile = self.summarise_room_pressure(state, features["remaining_supply"])
        flat_bot_profile = self.detect_flat_opponents(state)
        budget_discipline = self.compute_budget_discipline(state, need_level)

        features.update(
            {
                "need_level": need_level,
                "room_profile": room_profile,
                "flat_bot_profile": flat_bot_profile,
                "budget_discipline": budget_discipline,
            }
        )
        return features

    def compute_need_level(self, current_count, min_count):
        if current_count == 0:
            return 0
        if current_count == min_count:
            return 1
        if current_count == min_count + 1:
            return 2
        return 3

    def summarise_room_pressure(self, state, remaining_supply):
        current_painting = state["current_painting"]
        current_round = state["current_round"]
        starting_budget = state["starting_budget"]
        remaining_rounds = max(1, state["remaining_rounds"])

        urgent_prices = []
        market_pressure = []
        flat_floor = 0
        volatile_exists = False

        for opponent in state["opponents"]:
            wins = sum(opponent["paintings"].values())
            avg_price = (starting_budget - opponent["budget"]) / max(1, wins)
            opponent_min = min(opponent["paintings"].values())
            needs_current = opponent["paintings"][current_painting] == opponent_min

            if wins >= 3 and avg_price >= 15 and current_round < 80:
                volatile_exists = True

            if wins >= 5 and 8 <= avg_price <= 12:
                flat_floor = max(flat_floor, 10)
            elif wins >= 5 and 13 <= avg_price <= 17:
                flat_floor = max(flat_floor, 15)

            if not needs_current:
                continue

            urgent_prices.append(avg_price)
            market_pressure.append(opponent["budget"] / remaining_rounds)

        if not urgent_prices or max(urgent_prices) < 8:
            pressure_bin = 0
        elif max(urgent_prices) < 13:
            pressure_bin = 1
        elif max(urgent_prices) < 18:
            pressure_bin = 2
        else:
            pressure_bin = 3

        market = sum(market_pressure) / len(market_pressure) if market_pressure else 0.0
        scarcity_ratio = remaining_rounds / max(1, remaining_supply[current_painting])

        return {
            "is_small_room": state["room_size"] <= 5,
            "pressure_bin": pressure_bin,
            "market": market,
            "flat_floor": flat_floor,
            "volatile_exists": volatile_exists,
            "scarcity_ratio": scarcity_ratio,
        }

    def detect_flat_opponents(self, state):
        opponent_history = self.build_opponent_history(state)
        flat10_score = 0.0
        flat15_score = 0.0
        flat10_count = 0
        flat15_count = 0

        for opponent in state["opponents"]:
            history = opponent_history.get(opponent["bot_unique_id"], {})
            prices = []
            for artist in self.artists:
                prices.extend(history.get("prices_by_artist", {}).get(artist, []))

            wins = len(prices)
            if wins < 3:
                continue

            avg_price = sum(prices) / wins
            spread = max(prices) - min(prices)
            exact10_share = sum(price == 10 for price in prices) / wins
            exact15_share = sum(price == 15 for price in prices) / wins
            unique_prices = set(prices)

            flat10_like = 0.0
            flat15_like = 0.0

            if wins >= 2 and len(unique_prices) == 1:
                only_price = next(iter(unique_prices))
                if only_price == 10:
                    flat10_like = max(flat10_like, 0.90)
                elif only_price == 15:
                    flat15_like = max(flat15_like, 0.90)

            if 8 <= avg_price <= 12 and spread <= 2:
                flat10_like = max(flat10_like, 0.55)
            if 13 <= avg_price <= 17 and spread <= 2:
                flat15_like = max(flat15_like, 0.55)

            if wins >= 5 and 9 <= avg_price <= 11 and spread <= 1:
                flat10_like = max(flat10_like, 0.80)
            if wins >= 5 and 14 <= avg_price <= 16 and spread <= 1:
                flat15_like = max(flat15_like, 0.80)

            flat10_like = max(flat10_like, exact10_share)
            flat15_like = max(flat15_like, exact15_share)

            if flat10_like >= 0.55:
                flat10_count += 1
            if flat15_like >= 0.55:
                flat15_count += 1

            flat10_score = max(flat10_score, flat10_like)
            flat15_score = max(flat15_score, flat15_like)

        detected_floor = 0
        if flat15_score >= 0.55:
            detected_floor = 15
        elif flat10_score >= 0.55:
            detected_floor = 10

        return {
            "flat10_score": flat10_score,
            "flat15_score": flat15_score,
            "flat10_count": flat10_count,
            "flat15_count": flat15_count,
            "detected_floor": detected_floor,
        }

    def compute_budget_discipline(self, state, need_level):
        budget_ratio = state["my_budget"] / max(1, state["starting_budget"])
        spend_ratio = 1.0 - budget_ratio
        progress = state["progress"]
        remaining_rounds = max(1, state["remaining_rounds"])
        budget_per_remaining_round = state["my_budget"] / remaining_rounds
        long_game_factor = 0.0

        if state["round_limit"] > 75:
            long_game_factor = min(1.0, (state["round_limit"] - 75) / 75.0)

        reserve_factor = 1.0
        overspend_gap = spend_ratio - progress

        if long_game_factor > 0 and progress < 0.70 and need_level >= 2:
            reserve_factor *= 1.0 - 0.25 * long_game_factor
            if overspend_gap > 0.03:
                reserve_factor *= 0.78

        if long_game_factor > 0 and progress < 0.50 and need_level >= 2:
            if budget_per_remaining_round < 7:
                reserve_factor *= 0.82

        reserve_factor = max(0.65, min(1.0, reserve_factor))

        return {
            "budget_ratio": budget_ratio,
            "budget_per_remaining_round": budget_per_remaining_round,
            "spend_ratio": spend_ratio,
            "overspend_gap": overspend_gap,
            "long_game_factor": long_game_factor,
            "reserve_factor": reserve_factor,
        }

    def compute_floor_bid(
        self,
        need_level,
        scarcity_score,
        room_profile,
        flat_bot_profile,
        endgame_mode,
    ):
        pressure_bin = room_profile["pressure_bin"]
        detected_floor = max(
            room_profile["flat_floor"], flat_bot_profile["detected_floor"]
        )
        floor_bid = 0

        if need_level in (0, 1):
            if detected_floor >= 15:
                floor_bid = 16
            elif detected_floor >= 10:
                floor_bid = 11
            elif pressure_bin >= 2:
                floor_bid = 16 if not room_profile["is_small_room"] else 11
            elif pressure_bin == 1:
                floor_bid = 11
            elif need_level == 0:
                floor_bid = 10

            if scarcity_score >= 0.35 or endgame_mode != "normal":
                if detected_floor >= 15 or pressure_bin >= 2:
                    floor_bid = max(floor_bid, 16)
                elif floor_bid > 0:
                    floor_bid = max(floor_bid, 11)
        elif need_level == 2:
            if detected_floor >= 15:
                floor_bid = 16
            elif detected_floor >= 10:
                floor_bid = 11

        return floor_bid

    def compute_anchor_bid(self, state, features):
        current_painting = state["current_painting"]
        current_count = state["my_paintings"][current_painting]
        min_count = min(state["my_paintings"].values())
        lead = current_count - min_count
        remaining_rounds = max(1, state["remaining_rounds"])
        pace = state["my_budget"] / remaining_rounds
        market = features["room_profile"]["market"]
        scarcity_ratio = features["room_profile"]["scarcity_ratio"]
        need_level = features["need_level"]
        current_round = state["current_round"]
        floor_bid = self.compute_floor_bid(
            need_level=need_level,
            scarcity_score=features["scarcity_score"],
            room_profile=features["room_profile"],
            flat_bot_profile=features["flat_bot_profile"],
            endgame_mode=features["endgame_state"]["mode"],
        )

        marginal_gain = math.log(current_count + 2) - math.log(current_count + 1)
        anchor_bid = (
            pace
            * (
                0.8
                + 7.5 * marginal_gain
                - 0.25 * max(0, lead)
                + 0.28 * max(0.0, scarcity_ratio - 1.0)
            )
            + 0.7 * market
        )

        if need_level == 0:
            anchor_bid += 1
        elif current_round >= int(state["round_limit"] * 0.75) and need_level == 1:
            anchor_bid += 1

        anchor_bid = max(anchor_bid, floor_bid)

        if (
            features["room_profile"]["volatile_exists"]
            and current_round < 80
            and need_level == 3
        ):
            anchor_bid = min(anchor_bid * 0.45, 7)

        return max(0, min(state["my_budget"], anchor_bid))

    def decide_bid(self, state, features):
        my_budget = state["my_budget"]
        starting_budget = state["starting_budget"]
        progress = state["progress"]
        remaining_rounds = max(1, state["remaining_rounds"])
        current_round = state["current_round"]
        round_limit = state["round_limit"]

        marginal_gain = features["marginal_gain"]
        market_price = features["market_price"]
        scarcity_score = features["scarcity_score"]
        balance_pressure = features["balance_pressure"]
        total_pressure = features["opponent_model"]["total_pressure"]
        learned_adjustment = features["learned_adjustment"]
        endgame_state = features["endgame_state"]
        room_profile = features["room_profile"]
        flat_bot_profile = features["flat_bot_profile"]
        budget_discipline = features["budget_discipline"]
        need_level = features["need_level"]

        endgame_urgency = endgame_state["urgency"]
        endgame_mode = endgame_state["mode"]
        critical_need = need_level in (0, 1)
        flat_duel = state["room_size"] == 2 and flat_bot_profile["detected_floor"] > 0
        normalized_gain = math.sqrt(max(0, marginal_gain))
        anchor_bid = self.compute_anchor_bid(state, features)

        desire_score = (
            0.50 * normalized_gain
            + 10.0 * scarcity_score
            + 7.0 * balance_pressure
            + 5.0 * total_pressure
            + 8.0 * endgame_urgency
        )

        lift = desire_score / 8.0
        candidate_bid = market_price + lift + learned_adjustment

        if critical_need and room_profile["market"] > 0:
            candidate_bid += 0.25 * room_profile["market"]

        if progress < 0.25:
            candidate_bid *= 0.93
        elif progress > 0.80:
            candidate_bid *= 1.10

        if endgame_mode == "late_game":
            candidate_bid *= 1.06
        elif endgame_mode == "must_convert":
            candidate_bid *= 1.18

        budget_ratio = budget_discipline["budget_ratio"]
        budget_per_remaining_round = budget_discipline["budget_per_remaining_round"]

        if budget_ratio < 0.20:
            candidate_bid *= 0.78
        elif budget_ratio > 0.65 and progress > 0.60 and critical_need:
            candidate_bid *= 1.06

        if scarcity_score < 0.20 and balance_pressure < 0.30 and need_level == 3:
            candidate_bid *= 0.78

        if marginal_gain > 0 and balance_pressure >= 0.60:
            candidate_bid = max(candidate_bid, market_price + 1)

        if budget_discipline["long_game_factor"] > 0:
            blend = 0.40 + 0.40 * budget_discipline["long_game_factor"]
            if critical_need:
                blend *= 0.75
            if flat_duel and need_level <= 2:
                if round_limit <= 100:
                    blend *= 0.25
                else:
                    blend *= 0.55
            candidate_bid = (1.0 - blend) * candidate_bid + blend * anchor_bid

        if need_level >= 2 and not (flat_duel and need_level == 2):
            candidate_bid *= budget_discipline["reserve_factor"]

        floor_bid = self.compute_floor_bid(
            need_level=need_level,
            scarcity_score=scarcity_score,
            room_profile=room_profile,
            flat_bot_profile=flat_bot_profile,
            endgame_mode=endgame_mode,
        )

        if critical_need:
            candidate_bid = max(candidate_bid, floor_bid)
            if flat_bot_profile["detected_floor"] and round_limit <= 100:
                if scarcity_score >= 0.30 or total_pressure >= 0.45:
                    candidate_bid = max(candidate_bid, floor_bid + 1)
        elif need_level == 2 and flat_bot_profile["detected_floor"]:
            candidate_bid = max(candidate_bid, floor_bid)
        elif floor_bid > 0:
            candidate_bid = max(candidate_bid, min(floor_bid, market_price + 2))

        if flat_duel and need_level <= 2 and floor_bid > 0:
            flat_duel_floor = (
                floor_bid + 1 if round_limit <= 100 or need_level == 0 else floor_bid
            )
            candidate_bid = max(candidate_bid, flat_duel_floor)

        if progress < 0.33:
            phase_cap = max(12, int(my_budget * 0.08))
        elif progress < 0.75:
            phase_cap = max(14, int(my_budget * 0.14))
        else:
            phase_cap = max(20, int(my_budget * 0.30))

        if (
            budget_discipline["long_game_factor"] > 0
            and progress < 0.75
            and need_level >= 2
        ):
            if progress < 0.33:
                phase_cap = min(phase_cap, max(12, int(my_budget * 0.06)))
            else:
                phase_cap = min(phase_cap, max(14, int(my_budget * 0.10)))

        pacing_multiplier = 1.8
        if (
            budget_discipline["long_game_factor"] > 0
            and progress < 0.75
            and need_level >= 2
        ):
            pacing_multiplier = 1.20

        pacing_cap = max(10, int(budget_per_remaining_round * pacing_multiplier))
        hard_cap = min(my_budget, max(phase_cap, pacing_cap, floor_bid))

        if flat_duel and need_level <= 2 and floor_bid > 0:
            hard_cap = max(
                hard_cap,
                floor_bid + 1 if round_limit <= 100 or need_level == 0 else floor_bid,
            )

        if (
            budget_discipline["long_game_factor"] > 0
            and progress < 0.75
            and need_level >= 1
            and not (flat_duel and need_level <= 2)
        ):
            hard_cap = min(
                hard_cap,
                max(floor_bid, int(math.ceil(anchor_bid + 1))),
            )

        if endgame_mode == "late_game" and endgame_urgency >= 0.5:
            hard_cap = min(
                my_budget, max(hard_cap, int(budget_per_remaining_round * 2.3))
            )

        if endgame_mode == "must_convert":
            hard_cap = min(
                my_budget, max(hard_cap, int(budget_per_remaining_round * 3.5))
            )

        candidate_bid = min(candidate_bid, hard_cap)

        if endgame_mode == "must_convert" and endgame_urgency >= 0.6:
            candidate_bid = max(candidate_bid, market_price + 2, floor_bid)

        if room_profile["volatile_exists"] and current_round < 80:
            # Preserve i's conservative opening only for surplus artists.
            if need_level == 3:
                candidate_bid = min(candidate_bid * 0.60, max(7, market_price))
            elif critical_need and floor_bid == 0:
                cap = 11 if need_level == 0 or scarcity_score >= 0.35 else 10
                candidate_bid = min(candidate_bid, max(cap, market_price + 1))
            elif floor_bid > 0:
                candidate_bid = max(candidate_bid, floor_bid)

        jitter = self.stochastic_bid_jitter(state, features, candidate_bid)
        candidate_bid += jitter

        candidate_bid = min(candidate_bid, my_budget)
        candidate_bid = max(0, candidate_bid)

        if marginal_gain == 0 and scarcity_score < 0.15 and balance_pressure <= 0.10:
            if need_level == 3:
                return min(my_budget, max(0, market_price - 1))

        return int(math.floor(candidate_bid))
