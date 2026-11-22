import math

from bots.u5726455_i import Bot as LongAdvisorBot
from bots.u5726455_i2 import Bot as ShortAdvisorBot
from bots.u5726455_i2_i import Bot as BaseBot


class Bot(BaseBot):
    """
    Feature-approximation successor to i3.

    The bot keeps i3's robust opponent modelling and room-specific floors, but
    now groups the state into six explicit feature blocks:
    1. my collection state
    2. time and budget state
    3. future supply / scarcity
    4. opponent pressure
    5. market behaviour
    6. room structure

    A smooth weighted scorer combines those blocks, then blends the result with
    i3's anchor/floor logic so the policy stays stable in long auctions.
    """

    def __init__(self):
        super().__init__()
        self.name = "Weighted Strategy Blend"
        self.long_advisor = LongAdvisorBot()
        self.short_advisor = ShortAdvisorBot()

    def _clamp01(self, value):
        return max(0.0, min(1.0, value))

    def _mean(self, values):
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _recent_prices(self, state, artist):
        history_types = state["painting_order"][: len(state["amounts_paid"])]
        return [
            int(price)
            for price, seen_artist in zip(state["amounts_paid"], history_types)
            if seen_artist == artist
        ]

    def _collection_block(self, state, features):
        current_painting = state["current_painting"]
        paintings = state["my_paintings"]
        values = sorted(paintings.values())
        current_count = paintings[current_painting]
        min_count = values[0]
        second_min = values[1]
        max_count = values[-1]
        spread = max_count - min_count
        zero_count = sum(1 for value in values if value == 0)
        lead = current_count - min_count
        delta_product = max(0, int(features["marginal_gain"]))
        log_marginal = math.log(current_count + 2) - math.log(current_count + 1)

        if current_count == 0:
            repair_score = 1.0
        elif current_count == min_count:
            repair_score = 0.78
        elif current_count == min_count + 1:
            repair_score = 0.42
        else:
            repair_score = 0.08

        if current_count == min_count:
            balance_gap = second_min - min_count
        else:
            balance_gap = 0

        return {
            "current_count": current_count,
            "min_count": min_count,
            "max_count": max_count,
            "lead": lead,
            "spread": spread,
            "zero_count": zero_count,
            "is_zero": current_count == 0,
            "is_weakest": current_count == min_count,
            "is_near_weakest": current_count == min_count + 1,
            "delta_product": delta_product,
            "delta_product_signal": self._clamp01(math.log1p(delta_product) / 11.0),
            "log_marginal_gain": log_marginal,
            "repair_score": repair_score,
            "surplus_penalty": self._clamp01(max(0, lead) / 3.0),
            "balance_gap_signal": self._clamp01((spread + balance_gap) / 7.0),
        }

    def _time_budget_block(self, state):
        remaining_rounds = max(1, state["remaining_rounds"])
        my_budget = state["my_budget"]
        starting_budget = max(1, state["starting_budget"])
        opponent_budgets = [opponent["budget"] for opponent in state["opponents"]]
        opponent_paces = [
            opponent["budget"] / remaining_rounds for opponent in state["opponents"]
        ]
        my_pace = my_budget / remaining_rounds
        mean_opp_budget = self._mean(opponent_budgets)
        mean_opp_pace = self._mean(opponent_paces)
        budget_rank = 1 + sum(1 for budget in opponent_budgets if budget > my_budget)

        if state["round_limit"] <= 75:
            regime = "short"
        elif state["round_limit"] <= 125:
            regime = "medium"
        else:
            regime = "long"

        pace_edge = (my_pace - mean_opp_pace) / max(1.0, mean_opp_pace)
        budget_edge = (my_budget - mean_opp_budget) / starting_budget
        overspend_gap = state["progress"] - (my_budget / starting_budget)

        return {
            "regime": regime,
            "progress": state["progress"],
            "rounds_remaining": remaining_rounds,
            "budget": my_budget,
            "budget_fraction": my_budget / starting_budget,
            "pace": my_pace,
            "mean_opp_budget": mean_opp_budget,
            "mean_opp_pace": mean_opp_pace,
            "budget_rank": budget_rank,
            "pace_edge": pace_edge,
            "pace_edge_signal": self._clamp01(0.5 + 0.45 * pace_edge),
            "budget_edge": budget_edge,
            "budget_health": self._clamp01(
                (my_budget / starting_budget) + 0.35 * pace_edge
            ),
            "overspend_gap": overspend_gap,
            "overspend_signal": self._clamp01(1.0 - max(0.0, overspend_gap) * 1.8),
            "late_spending_window": self._clamp01((state["progress"] - 0.55) / 0.35),
        }

    def _supply_block(self, state, features, collection_block):
        current_painting = state["current_painting"]
        remaining_supply = features["remaining_supply"]
        future_window_supply = features["future_window_supply"]
        remaining_current = remaining_supply[current_painting]
        remaining_rounds = max(1, state["remaining_rounds"])
        near_8 = future_window_supply[8][current_painting]
        near_20 = future_window_supply[20][current_painting]
        near_50 = future_window_supply[50][current_painting]
        scarcity_ratio = remaining_rounds / max(1, remaining_current)

        sorted_supply = sorted(remaining_supply.items(), key=lambda item: item[1])
        scarcity_rank = next(
            (
                idx
                for idx, (artist, _count) in enumerate(sorted_supply)
                if artist == current_painting
            ),
            0,
        )
        scarcity_rank_signal = 1.0 - (scarcity_rank / max(1, len(sorted_supply) - 1))

        future_zero_repair_risk = 0.0
        if collection_block["is_zero"]:
            if remaining_current <= 2 or near_8 == 0:
                future_zero_repair_risk = 1.0
            elif remaining_current <= 4 or near_20 <= 1:
                future_zero_repair_risk = 0.75
            else:
                future_zero_repair_risk = 0.40
        elif collection_block["is_weakest"] and remaining_current <= 3:
            future_zero_repair_risk = 0.45

        if near_8 == 0:
            window_pressure = 1.0
        elif near_8 == 1:
            window_pressure = 0.75
        elif near_20 <= 2:
            window_pressure = 0.45
        elif near_50 <= 5:
            window_pressure = 0.20
        else:
            window_pressure = 0.05

        return {
            "remaining_current": remaining_current,
            "near_8": near_8,
            "near_20": near_20,
            "near_50": near_50,
            "scarcity_ratio": scarcity_ratio,
            "scarcity_score": features["scarcity_score"],
            "scarcity_rank_signal": scarcity_rank_signal,
            "future_zero_repair_risk": future_zero_repair_risk,
            "window_pressure": window_pressure,
        }

    def _pressure_block(self, state, features):
        current_painting = state["current_painting"]
        remaining_rounds = max(1, state["remaining_rounds"])
        needers = []
        near_needers = []
        zero_needers = 0

        for opponent in state["opponents"]:
            opponent_min = min(opponent["paintings"].values())
            opponent_count = opponent["paintings"][current_painting]
            if opponent_count == opponent_min:
                needers.append(opponent)
                if opponent_count == 0:
                    zero_needers += 1
            elif opponent_count == opponent_min + 1:
                near_needers.append(opponent)

        needer_budgets = [bot["budget"] for bot in needers]
        needer_paces = [bot["budget"] / remaining_rounds for bot in needers]
        strongest_threat = features["opponent_model"]["strongest_threat"]
        total_pressure = features["opponent_model"]["total_pressure"]
        need_fraction = len(needers) / max(1, len(state["opponents"]))
        budgeted_need_signal = self._clamp01(self._mean(needer_paces) / 14.0)
        max_needer_signal = self._clamp01(max(needer_paces, default=0.0) / 20.0)
        pressure_bin_signal = self._clamp01(
            features["room_profile"]["pressure_bin"] / 3.0
        )

        contention_signal = self._clamp01(
            0.36 * need_fraction
            + 0.22 * budgeted_need_signal
            + 0.16 * max_needer_signal
            + 0.16 * total_pressure
            + 0.10 * pressure_bin_signal
        )

        return {
            "num_needers": len(needers),
            "num_near_needers": len(near_needers),
            "zero_needers": zero_needers,
            "need_fraction": need_fraction,
            "mean_needer_budget": self._mean(needer_budgets),
            "max_needer_budget": max(needer_budgets, default=0.0),
            "mean_needer_pace": self._mean(needer_paces),
            "max_needer_pace": max(needer_paces, default=0.0),
            "strongest_threat": strongest_threat,
            "total_pressure": total_pressure,
            "contention_signal": contention_signal,
        }

    def _market_block(self, state, features, pressure_block):
        current_painting = state["current_painting"]
        amounts_paid = [int(price) for price in state["amounts_paid"]]
        type_prices = self._recent_prices(state, current_painting)
        recent_all = amounts_paid[-10:] if amounts_paid else []
        recent_type = type_prices[-6:] if type_prices else []
        last_type_price = type_prices[-1] if type_prices else 0
        last_price = amounts_paid[-1] if amounts_paid else 0

        recent_type_mean = self._mean(recent_type)
        recent_all_mean = self._mean(recent_all)
        type_reference = max(
            features["market_price"],
            self.robust_median(recent_type) if recent_type else 0,
            self.robust_median(recent_all) if recent_all else 0,
        )

        if len(recent_type) >= 4:
            earlier = self._mean(recent_type[-4:-2])
            later = self._mean(recent_type[-2:])
            type_trend = (later - earlier) / max(1.0, earlier)
        else:
            type_trend = 0.0

        clear_floor = max(
            features["room_profile"]["flat_floor"],
            features["flat_bot_profile"]["detected_floor"],
        )

        market_heat = self._clamp01(
            0.45 * self._clamp01(type_reference / 18.0)
            + 0.20 * self._clamp01(recent_type_mean / 18.0)
            + 0.15 * self._clamp01(recent_all_mean / 18.0)
            + 0.10 * self._clamp01((type_trend + 0.25) / 0.50)
            + 0.10 * pressure_block["contention_signal"]
        )

        learned_signal = self._clamp01((features["learned_adjustment"] + 3.0) / 7.0)

        return {
            "last_price": last_price,
            "last_type_price": last_type_price,
            "recent_type_mean": recent_type_mean,
            "recent_all_mean": recent_all_mean,
            "type_reference": type_reference,
            "type_trend": type_trend,
            "clear_floor": clear_floor,
            "market_heat": market_heat,
            "learned_signal": learned_signal,
        }

    def _room_block(self, state, features, pressure_block):
        room_size = state["room_size"]
        opponents = state["opponents"]
        active_bidders = 1 + sum(1 for opponent in opponents if opponent["budget"] > 0)
        flat_bot_profile = features["flat_bot_profile"]
        flat_count = flat_bot_profile["flat10_count"] + flat_bot_profile["flat15_count"]
        baseline_heavy = flat_count / max(1, len(opponents))
        crowding = self._clamp01((room_size - 2) / 6.0)
        volatility = 1.0 if features["room_profile"]["volatile_exists"] else 0.0
        structure_intensity = self._clamp01(
            0.40 * crowding
            + 0.30 * baseline_heavy
            + 0.20 * volatility
            + 0.10 * pressure_block["contention_signal"]
        )

        return {
            "room_size": room_size,
            "active_bidders": active_bidders,
            "baseline_heavy": baseline_heavy,
            "crowding": crowding,
            "volatility": volatility,
            "structure_intensity": structure_intensity,
        }

    def _approximation_block(
        self,
        state,
        features,
        collection_block,
        time_budget_block,
        supply_block,
        pressure_block,
        market_block,
        room_block,
    ):
        collection_signal = self._clamp01(
            0.42 * collection_block["repair_score"]
            + 0.22 * collection_block["delta_product_signal"]
            + 0.18 * collection_block["balance_gap_signal"]
            + 0.18 * (1.0 - collection_block["surplus_penalty"])
        )

        time_signal = self._clamp01(
            0.40 * time_budget_block["budget_health"]
            + 0.28 * time_budget_block["pace_edge_signal"]
            + 0.18 * time_budget_block["overspend_signal"]
            + 0.14 * time_budget_block["late_spending_window"]
        )

        supply_signal = self._clamp01(
            0.46 * supply_block["scarcity_score"]
            + 0.24 * supply_block["window_pressure"]
            + 0.18 * supply_block["future_zero_repair_risk"]
            + 0.12 * supply_block["scarcity_rank_signal"]
        )

        pressure_signal = self._clamp01(
            0.48 * pressure_block["contention_signal"]
            + 0.22 * pressure_block["strongest_threat"]
            + 0.20 * pressure_block["total_pressure"]
            + 0.10 * self._clamp01(pressure_block["zero_needers"] / 3.0)
        )

        market_signal = self._clamp01(
            0.50 * market_block["market_heat"]
            + 0.20 * market_block["learned_signal"]
            + 0.20 * self._clamp01((market_block["type_trend"] + 0.25) / 0.50)
            + 0.10 * self._clamp01(market_block["clear_floor"] / 16.0)
        )

        room_signal = self._clamp01(
            0.55 * room_block["structure_intensity"]
            + 0.20 * room_block["baseline_heavy"]
            + 0.15 * room_block["crowding"]
            + 0.10 * room_block["volatility"]
        )

        regime = time_budget_block["regime"]
        if regime == "short":
            weights = {
                "collection": 0.24,
                "time": 0.12,
                "supply": 0.18,
                "pressure": 0.20,
                "market": 0.18,
                "room": 0.08,
            }
            premium_bias = 5.0
            anchor_mix = 0.28
        elif regime == "medium":
            weights = {
                "collection": 0.26,
                "time": 0.14,
                "supply": 0.20,
                "pressure": 0.18,
                "market": 0.14,
                "room": 0.08,
            }
            premium_bias = 4.2
            anchor_mix = 0.42
        else:
            weights = {
                "collection": 0.28,
                "time": 0.18,
                "supply": 0.22,
                "pressure": 0.14,
                "market": 0.10,
                "room": 0.08,
            }
            premium_bias = 3.4
            anchor_mix = 0.64

        blended_signal = (
            weights["collection"] * collection_signal
            + weights["time"] * time_signal
            + weights["supply"] * supply_signal
            + weights["pressure"] * pressure_signal
            + weights["market"] * market_signal
            + weights["room"] * room_signal
        )

        premium_scale = (
            premium_bias
            + 0.28 * time_budget_block["pace"]
            + 2.6 * pressure_signal
            + 1.8 * supply_signal
            + 1.2 * collection_signal
        )

        market_reference = max(
            market_block["type_reference"],
            market_block["clear_floor"],
            1,
        )

        return {
            "collection_signal": collection_signal,
            "time_signal": time_signal,
            "supply_signal": supply_signal,
            "pressure_signal": pressure_signal,
            "market_signal": market_signal,
            "room_signal": room_signal,
            "blended_signal": blended_signal,
            "premium_scale": premium_scale,
            "market_reference": market_reference,
            "anchor_mix": anchor_mix,
        }

    def extract_features(self, state):
        features = super().extract_features(state)
        collection_block = self._collection_block(state, features)
        time_budget_block = self._time_budget_block(state)
        supply_block = self._supply_block(state, features, collection_block)
        pressure_block = self._pressure_block(state, features)
        market_block = self._market_block(state, features, pressure_block)
        room_block = self._room_block(state, features, pressure_block)
        approximation_block = self._approximation_block(
            state=state,
            features=features,
            collection_block=collection_block,
            time_budget_block=time_budget_block,
            supply_block=supply_block,
            pressure_block=pressure_block,
            market_block=market_block,
            room_block=room_block,
        )

        features.update(
            {
                "collection_block": collection_block,
                "time_budget_block": time_budget_block,
                "supply_block": supply_block,
                "pressure_block": pressure_block,
                "market_block": market_block,
                "room_block": room_block,
                "approximation_block": approximation_block,
            }
        )
        return features

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
        approx_bid = self.decide_bid(state, features)
        final_bid = approx_bid

        if round_limit >= 150:
            long_bid = self.long_advisor.get_bid(
                current_round=current_round,
                bots=bots,
                winner_pays=winner_pays,
                artists_and_values=artists_and_values,
                round_limit=round_limit,
                starting_budget=starting_budget,
                painting_order=painting_order,
                target_collection=target_collection,
                my_bot_details=my_bot_details,
                current_painting=current_painting,
                winner_ids=winner_ids,
                amounts_paid=amounts_paid,
            )
            if features["need_level"] >= 2:
                final_bid = int(math.floor(0.60 * long_bid + 0.40 * approx_bid))
            else:
                final_bid = int(math.floor(0.45 * long_bid + 0.55 * approx_bid))
        elif round_limit <= 75 and (
            features["room_block"]["baseline_heavy"] >= 0.30 or state["room_size"] <= 5
        ):
            short_bid = self.short_advisor.get_bid(
                current_round=current_round,
                bots=bots,
                winner_pays=winner_pays,
                artists_and_values=artists_and_values,
                round_limit=round_limit,
                starting_budget=starting_budget,
                painting_order=painting_order,
                target_collection=target_collection,
                my_bot_details=my_bot_details,
                current_painting=current_painting,
                winner_ids=winner_ids,
                amounts_paid=amounts_paid,
            )
            if features["need_level"] <= 1:
                final_bid = int(math.floor(0.82 * approx_bid + 0.18 * short_bid))
            else:
                final_bid = int(math.floor(0.90 * approx_bid + 0.10 * short_bid))

        return int(max(0, min(state["my_budget"], final_bid)))

    def decide_bid(self, state, features):
        my_budget = state["my_budget"]
        current_round = state["current_round"]
        round_limit = state["round_limit"]
        base_bid = super().decide_bid(state, features)

        need_level = features["need_level"]
        critical_need = need_level in (0, 1)
        endgame_state = features["endgame_state"]
        room_profile = features["room_profile"]
        flat_bot_profile = features["flat_bot_profile"]
        budget_discipline = features["budget_discipline"]
        collection_block = features["collection_block"]
        time_budget_block = features["time_budget_block"]
        supply_block = features["supply_block"]
        pressure_block = features["pressure_block"]
        market_block = features["market_block"]
        room_block = features["room_block"]
        approximation_block = features["approximation_block"]

        floor_bid = self.compute_floor_bid(
            need_level=need_level,
            scarcity_score=supply_block["scarcity_score"],
            room_profile=room_profile,
            flat_bot_profile=flat_bot_profile,
            endgame_mode=endgame_state["mode"],
        )
        anchor_bid = self.compute_anchor_bid(state, features)

        model_bid = (
            approximation_block["market_reference"]
            + approximation_block["premium_scale"]
            * approximation_block["blended_signal"]
        )

        if critical_need and room_profile["market"] > 0:
            model_bid += 0.20 * room_profile["market"]
        if critical_need and supply_block["future_zero_repair_risk"] >= 0.75:
            model_bid += 1.2
        if need_level == 2 and supply_block["window_pressure"] >= 0.75:
            model_bid += 0.8

        regime = time_budget_block["regime"]
        if regime == "short":
            candidate_bid = 0.88 * base_bid + 0.12 * max(model_bid, floor_bid)
        elif regime == "medium":
            candidate_bid = 0.62 * base_bid + 0.23 * model_bid + 0.15 * anchor_bid
        else:
            candidate_bid = 0.42 * base_bid + 0.28 * model_bid + 0.30 * anchor_bid

        if regime == "short":
            if critical_need and floor_bid > 0:
                candidate_bid = max(candidate_bid, floor_bid + 1)
        elif regime == "long" and need_level >= 2:
            candidate_bid *= budget_discipline["reserve_factor"]

        if (
            collection_block["surplus_penalty"] >= 0.65
            and supply_block["scarcity_score"] < 0.28
        ):
            candidate_bid *= 0.78

        if room_profile["volatile_exists"] and current_round < min(
            80, round_limit // 2
        ):
            if need_level == 3:
                candidate_bid = min(
                    candidate_bid,
                    max(7, market_block["type_reference"]),
                )
            elif not critical_need:
                candidate_bid *= 0.88

        if endgame_state["mode"] == "late_game":
            candidate_bid *= 1.05
        elif endgame_state["mode"] == "must_convert":
            candidate_bid *= 1.14

        if critical_need:
            candidate_bid = max(candidate_bid, floor_bid)
        elif need_level == 2 and floor_bid > 0:
            candidate_bid = max(
                candidate_bid, min(floor_bid, market_block["type_reference"] + 2)
            )

        flat_duel = state["room_size"] == 2 and flat_bot_profile["detected_floor"] > 0
        if flat_duel and need_level <= 2 and floor_bid > 0:
            if round_limit <= 100 or need_level == 0:
                candidate_bid = max(candidate_bid, floor_bid + 1)
            else:
                candidate_bid = max(candidate_bid, floor_bid)

        progress = state["progress"]
        pace = time_budget_block["pace"]
        if regime == "short":
            if progress < 0.40:
                phase_cap = max(18, int(my_budget * 0.18))
            else:
                phase_cap = max(24, int(my_budget * 0.34))
            pacing_mult = 2.8 if critical_need else 1.9
        elif regime == "medium":
            if progress < 0.33:
                phase_cap = max(15, int(my_budget * 0.10))
            elif progress < 0.75:
                phase_cap = max(18, int(my_budget * 0.16))
            else:
                phase_cap = max(24, int(my_budget * 0.28))
            pacing_mult = 2.3 if critical_need else 1.6
        else:
            if progress < 0.33:
                phase_cap = max(12, int(my_budget * 0.07))
            elif progress < 0.75:
                phase_cap = max(14, int(my_budget * 0.12))
            else:
                phase_cap = max(20, int(my_budget * 0.26))
            pacing_mult = 2.0 if critical_need else 1.2

        if regime == "long" and progress < 0.75 and need_level >= 2:
            phase_cap = min(phase_cap, max(floor_bid, int(anchor_bid + 1)))

        pacing_cap = max(floor_bid, int(pace * pacing_mult))
        hard_cap = min(my_budget, max(phase_cap, pacing_cap, floor_bid))

        if endgame_state["mode"] == "late_game" and endgame_state["urgency"] >= 0.50:
            hard_cap = min(my_budget, max(hard_cap, int(pace * 2.6)))
        if endgame_state["mode"] == "must_convert":
            hard_cap = min(my_budget, max(hard_cap, int(pace * 4.0)))

        if regime == "long" and progress < 0.70 and need_level >= 1 and not flat_duel:
            hard_cap = min(hard_cap, max(floor_bid, int(math.ceil(anchor_bid + 1))))

        if (
            collection_block["is_zero"]
            and supply_block["future_zero_repair_risk"] >= 0.75
            and pressure_block["contention_signal"] >= 0.45
        ):
            hard_cap = min(my_budget, max(hard_cap, floor_bid + 2, int(pace * 3.0)))

        candidate_bid = min(candidate_bid, hard_cap)

        jitter = self.stochastic_bid_jitter(state, features, candidate_bid)
        candidate_bid += jitter

        if (
            features["marginal_gain"] == 0
            and supply_block["scarcity_score"] < 0.15
            and collection_block["surplus_penalty"] >= 0.66
        ):
            return int(max(0, min(my_budget, market_block["type_reference"] - 1)))

        return int(max(0, min(my_budget, math.floor(candidate_bid))))
