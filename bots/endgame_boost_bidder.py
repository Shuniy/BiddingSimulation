import math
from collections import Counter
from statistics import mean


class Bot(object):
    ARTISTS = ("Da Vinci", "Picasso", "Rembrandt", "Van Gogh")

    def __init__(self):
        self.name = "Endgame Boost Bidder"
        self.last_round = -1
        self.last_painting = None
        self.last_bid = 0
        self.last_needed = False
        self.regret = {artist: 0 for artist in self.ARTISTS}

    # =========================
    # Core helpers from strong base bot
    # =========================
    def _remaining_counts(self, painting_order, current_round):
        return Counter(painting_order[current_round:])

    def _update_regret(self, current_round, my_unique_id, winner_ids, amounts_paid):
        if (
            current_round == 0
            or self.last_painting is None
            or self.last_round != current_round - 1
            or len(winner_ids) < current_round
            or len(amounts_paid) < current_round
        ):
            return

        winner = winner_ids[-1]
        amount_paid = amounts_paid[-1]

        if (
            self.last_needed
            and self.last_bid > 0
            and winner != my_unique_id
            and amount_paid <= self.last_bid + 2
        ):
            self.regret[self.last_painting] = min(
                self.regret[self.last_painting] + 1,
                4,
            )
        elif not self.last_needed and winner == my_unique_id and amount_paid >= 12:
            self.regret[self.last_painting] = max(
                self.regret[self.last_painting] - 1,
                0,
            )

    # =========================
    # Minimal enhancements from our bot
    # =========================
    def _compute_opponent_pressure(
        self,
        bots,
        my_unique_id,
        current_painting,
        my_current_count,
        starting_budget,
        my_score,
    ):
        """
        Very mild version of our opponent modelling.
        Returns a value in [0,1].
        """
        pressures = []

        for bot in bots:
            if bot["bot_unique_id"] == my_unique_id:
                continue

            opp_count = bot["paintings"][current_painting]
            opp_need = 1.0 / (opp_count + 1)

            if opp_count < my_current_count:
                opp_need += 0.15

            budget_strength = bot["budget"] / max(1, starting_budget)

            if bot["score"] < my_score:
                score_gap = (my_score - bot["score"]) / max(1, my_score)
                score_pressure = min(1.0, 0.4 + score_gap)
            else:
                score_pressure = 0.4

            threat = (
                0.50 * min(1.0, opp_need)
                + 0.30 * min(1.0, budget_strength)
                + 0.20 * score_pressure
            )
            pressures.append(min(1.0, threat))

        if not pressures:
            return 0.0

        strongest = max(pressures)
        average = sum(pressures) / len(pressures)
        return min(1.0, 0.65 * strongest + 0.35 * average)

    def _endgame_bonus(
        self,
        current_round,
        round_limit,
        remaining_rounds,
        current_count,
        min_count,
        scarcity,
    ):
        """
        Mild earlier endgame pressure.
        Only returns small integer bump.
        """
        progress = current_round / max(1, round_limit)

        bonus = 0
        if progress >= 0.65 and current_count == min_count:
            bonus += 1
        if progress >= 0.88 and current_count == min_count:
            bonus += 1
        if remaining_rounds <= 15 and scarcity > 1.2:
            bonus += 1

        return min(2, bonus)

    def _deterministic_jitter(self, current_round, current_painting):
        """
        Tiny anti-predictability jitter in {-1, 0, +1}.
        """
        seed = (current_round * 17 + len(current_painting) * 13) % 5
        if seed == 0:
            return -1
        elif seed == 1:
            return 1
        return 0

    def _apply_minimal_enhancements(
        self,
        raw_bid,
        bots,
        my_unique_id,
        current_painting,
        my_bot_details,
        starting_budget,
        current_round,
        round_limit,
        remaining_rounds,
        scarcity,
        needed,
    ):
        counts = my_bot_details["paintings"]
        my_current_count = counts[current_painting]
        min_count = min(counts.values())
        my_score = my_bot_details["score"]

        # 1) Mild opponent pressure bump
        opponent_pressure = self._compute_opponent_pressure(
            bots=bots,
            my_unique_id=my_unique_id,
            current_painting=current_painting,
            my_current_count=my_current_count,
            starting_budget=starting_budget,
            my_score=my_score,
        )

        if needed:
            if opponent_pressure >= 0.75:
                raw_bid += 2
            elif opponent_pressure >= 0.50:
                raw_bid += 1

        # 2) Mild earlier endgame bump
        raw_bid += self._endgame_bonus(
            current_round=current_round,
            round_limit=round_limit,
            remaining_rounds=remaining_rounds,
            current_count=my_current_count,
            min_count=min_count,
            scarcity=scarcity,
        )

        # 3) Tiny jitter
        jitter = self._deterministic_jitter(current_round, current_painting)
        raw_bid += jitter

        return raw_bid

    # =========================
    # Base bot room summaries
    # =========================
    def _summarise_small_room(
        self,
        bots,
        my_unique_id,
        current_painting,
        current_round,
        starting_budget,
        remaining_rounds,
    ):
        market_pressure = []
        flat_floor = 0
        volatile_exists = False

        for bot in bots:
            if bot["bot_unique_id"] == my_unique_id:
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
        return market, flat_floor, volatile_exists

    def _summarise_large_room(
        self,
        bots,
        my_unique_id,
        current_painting,
        current_round,
        starting_budget,
        remaining_rounds,
    ):
        urgent_prices = []
        market_pressure = []
        flat_floor = 0
        volatile_exists = False

        for bot in bots:
            if bot["bot_unique_id"] == my_unique_id:
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
        return pressure_bin, market, flat_floor, volatile_exists

    # =========================
    # Base bot small room logic
    # =========================
    def _small_room_bid(
        self,
        current_round,
        bots,
        round_limit,
        starting_budget,
        painting_order,
        my_bot_details,
        current_painting,
    ):
        my_budget = my_bot_details["budget"]
        counts = my_bot_details["paintings"]
        min_count = min(counts.values())
        current_count = counts[current_painting]
        lead = current_count - min_count

        remaining_counts = self._remaining_counts(painting_order, current_round)
        remaining_rounds = max(1, round_limit - current_round)
        remaining_current = max(1, remaining_counts[current_painting])
        scarcity = remaining_rounds / remaining_current
        marginal_gain = math.log(current_count + 2) - math.log(current_count + 1)

        market, flat_floor, volatile_exists = self._summarise_small_room(
            bots=bots,
            my_unique_id=my_bot_details["bot_unique_id"],
            current_painting=current_painting,
            current_round=current_round,
            starting_budget=starting_budget,
            remaining_rounds=remaining_rounds,
        )

        raw_bid = (my_budget / remaining_rounds) * (
            0.8
            + 7.5 * marginal_gain
            - 0.25 * max(0, lead)
            + 0.25 * max(0.0, scarcity - 1.0)
        ) + 0.7 * market

        if min_count == 0:
            if current_count == 0:
                raw_bid += 1
        elif current_round >= 150:
            if lead == 0:
                raw_bid += 1
            if scarcity > 1.2:
                raw_bid += 1

        if current_count == 0:
            raw_bid = max(raw_bid, max(flat_floor, 10))
            if scarcity > 1.2 or current_round > 150:
                raw_bid = max(raw_bid, 11)
        elif lead == 0 and flat_floor:
            raw_bid = max(raw_bid, 10)

        if volatile_exists and current_round < 80:
            if lead == 0:
                cap = 11 if current_count == 0 or scarcity > 1.2 else 10
                raw_bid = min(raw_bid, cap)
            else:
                raw_bid = min(raw_bid * 0.45, 7)

        needed = lead == 0

        # Minimal safe enhancements
        raw_bid = self._apply_minimal_enhancements(
            raw_bid=raw_bid,
            bots=bots,
            my_unique_id=my_bot_details["bot_unique_id"],
            current_painting=current_painting,
            my_bot_details=my_bot_details,
            starting_budget=starting_budget,
            current_round=current_round,
            round_limit=round_limit,
            remaining_rounds=remaining_rounds,
            scarcity=scarcity,
            needed=needed,
        )

        bid = int(max(0, min(my_budget, raw_bid)))
        return bid, needed

    # =========================
    # Base bot large room logic
    # =========================
    def _large_room_bid(
        self,
        current_round,
        bots,
        round_limit,
        starting_budget,
        painting_order,
        my_bot_details,
        current_painting,
    ):
        my_budget = my_bot_details["budget"]
        counts = my_bot_details["paintings"]
        min_count = min(counts.values())
        current_count = counts[current_painting]
        lead = current_count - min_count

        remaining_counts = self._remaining_counts(painting_order, current_round)
        remaining_rounds = max(1, round_limit - current_round)
        remaining_current = max(1, remaining_counts[current_painting])
        scarcity = remaining_rounds / remaining_current
        pace = my_budget / remaining_rounds
        marginal_gain = math.log(current_count + 2) - math.log(current_count + 1)

        pressure_bin, market, flat_floor, volatile_exists = self._summarise_large_room(
            bots=bots,
            my_unique_id=my_bot_details["bot_unique_id"],
            current_painting=current_painting,
            current_round=current_round,
            starting_budget=starting_budget,
            remaining_rounds=remaining_rounds,
        )

        raw_bid = (
            pace
            * (
                0.8
                + 7.5 * marginal_gain
                - 0.25 * max(0, lead)
                + 0.28 * max(0.0, scarcity - 1.0)
            )
            + 0.7 * market
            + 0.8 * self.regret[current_painting]
        )

        if current_count == 0:
            need_level = 0
        elif current_count == min_count:
            need_level = 1
        elif current_count == min_count + 1:
            need_level = 2
        else:
            need_level = 3

        if need_level == 0:
            raw_bid += 1
        elif current_round >= 150 and lead == 0:
            raw_bid += 1

        if current_round >= 150 and scarcity > 1.2:
            raw_bid += 1

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

            if scarcity > 1.3:
                floor = max(
                    floor,
                    16 if pressure_bin >= 1 or flat_floor >= 15 else 11,
                )

            if len(bots) >= 9 and scarcity > 1.45 and need_level == 0:
                floor = max(floor, 20)

            raw_bid = max(raw_bid, floor)
        elif need_level == 2:
            raw_bid = max(raw_bid, pace if pressure_bin == 0 else max(pace, 10))
            if flat_floor >= 15 and scarcity > 1.25:
                raw_bid = max(raw_bid, 16)
        else:
            raw_bid = min(raw_bid, max(0, pace * 0.8))

        if volatile_exists and current_round < 80:
            if lead == 0:
                cap = 11 if current_count == 0 or scarcity > 1.2 else 10
                if flat_floor >= 15 or pressure_bin >= 2:
                    cap = 16
                raw_bid = min(raw_bid, cap)
            else:
                raw_bid = min(raw_bid * 0.45, 7)

        needed = need_level in (0, 1)

        # Minimal safe enhancements
        raw_bid = self._apply_minimal_enhancements(
            raw_bid=raw_bid,
            bots=bots,
            my_unique_id=my_bot_details["bot_unique_id"],
            current_painting=current_painting,
            my_bot_details=my_bot_details,
            starting_budget=starting_budget,
            current_round=current_round,
            round_limit=round_limit,
            remaining_rounds=remaining_rounds,
            scarcity=scarcity,
            needed=needed,
        )

        bid = int(max(0, min(my_budget, raw_bid)))
        return bid, needed

    # =========================
    # Main bidding entry
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
        my_budget = my_bot_details["budget"]
        my_unique_id = my_bot_details["bot_unique_id"]

        self._update_regret(current_round, my_unique_id, winner_ids, amounts_paid)

        if my_budget <= 0:
            self._store_last_round_info(current_round, current_painting, 0, False)
            return 0

        if len(bots) <= 5:
            bid, needed = self._small_room_bid(
                current_round=current_round,
                bots=bots,
                round_limit=round_limit,
                starting_budget=starting_budget,
                painting_order=painting_order,
                my_bot_details=my_bot_details,
                current_painting=current_painting,
            )
        else:
            bid, needed = self._large_room_bid(
                current_round=current_round,
                bots=bots,
                round_limit=round_limit,
                starting_budget=starting_budget,
                painting_order=painting_order,
                my_bot_details=my_bot_details,
                current_painting=current_painting,
            )

        self._store_last_round_info(current_round, current_painting, bid, needed)
        return bid

    def _store_last_round_info(self, current_round, current_painting, bid, needed):
        self.last_round = current_round
        self.last_painting = current_painting
        self.last_bid = bid
        self.last_needed = needed
