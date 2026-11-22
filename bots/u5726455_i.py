"""
Improved heuristic bot with separate small-room and large-room handling.

Methodology:
1. Count remaining paintings to estimate scarcity.
2. Compare the current artist count to the minimum artist count to determine
   whether the current artist is a scoring bottleneck.
3. Estimate room pressure by looking at opponents who currently need the same
   artist.
4. Update a small regret memory after narrow misses.
5. Use one bidding overlay for small rooms and another for large rooms, because
   the original design assumes price bands behave differently as the room grows.

Design choices:
- This keeps the original logic exactly.
- The main original design choice is the split between small-room and
  large-room strategies.
- Only comments and methodology notes were added here.
"""

import math
from collections import Counter
from statistics import mean


class Bot(object):
    ARTISTS = ("Da Vinci", "Picasso", "Rembrandt", "Van Gogh")

    def __init__(self):
        self.name = "Room-Size Bidder"
        self.last_round = -1
        self.last_painting = None
        self.last_bid = 0
        self.last_needed = False
        self.regret = {artist: 0 for artist in self.ARTISTS}

    def _remaining_counts(self, painting_order, current_round):
        """Count remaining supply from the current round onward."""

        return Counter(painting_order[current_round:])

    def _update_regret(self, current_round, my_unique_id, winner_ids, amounts_paid):
        """Increase regret after a narrow loss on a needed artist."""

        # base case checks to ensure we have the necessary information to update regret, and that we're not trying to update based on an incomplete or irrelevant round outcome.
        if (
            current_round == 0
            or self.last_painting is None
            or self.last_round != current_round - 1
            or len(winner_ids) < current_round
            or len(amounts_paid) < current_round
        ):
            return

        # winner_ids and amounts_paid are expected to be lists of length equal to the current round number, where the last element corresponds to the most recent round. We check that they have enough elements before trying to access the last one.
        winner = winner_ids[-1]
        amount_paid = amounts_paid[-1]

        # if we narrowly lost a needed painting (last_bid was close to winning and the winner was someone else), we increase regret for that painting, which will make us bid more aggressively on it in the future. If we won a painting that we didn't need at a high price, we decrease regret for that painting, which will make us bid less aggressively on it in the future. This allows the bot to learn from its bidding outcomes and adjust its strategy over time.
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

    def _summarise_small_room(
        self,
        bots,
        my_unique_id,
        current_painting,
        current_round,
        starting_budget,
        remaining_rounds,
    ):
        """Estimate market pressure in a small room."""

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
        """Estimate pressure bands in a larger room."""

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
            # this is the difference, in a larger room we might see more opponents
            # who are under pressure but haven't hit the 8-12 band yet,
            # so we also consider a slightly higher band for setting a stronger flat floor.
            elif wins >= 5 and 13 <= avg_price <= 17:
                flat_floor = max(flat_floor, 15)

            if not needs_current:
                continue

            # urgent_prices is a new concept for the large room,
            # where we track the average prices of opponents who need the current painting,
            # to estimate how much pressure there is on this painting.
            # If we see opponents with high average prices who need this painting,
            # it suggests that there will be strong competition for it,
            # which can inform our bidding strategy.
            urgent_prices.append(avg_price)
            market_pressure.append(bot["budget"] / max(1, remaining_rounds))

        # unlike the small room where we only had a flat floor based on certain conditions,
        # in the large room we use the distribution of urgent_prices to
        # categorize the pressure into bins.
        # This allows us to have a more nuanced understanding of the competitive landscape
        # for this painting, which can inform our bidding strategy in a more granular way.
        # urgent_prices is expected to contain the average prices of opponents who need the current painting,
        # so we look at the maximum of these prices to determine the pressure bin.
        # If there are no urgent_prices, we consider it as no pressure (bin 0).
        # If the maximum urgent price is below 8, it's low pressure (bin 0).
        #  If it's between 8 and 13, it's moderate pressure (bin 1).
        # If it's between 13 and 18, it's high pressure (bin 2).
        # If it's above 18, it's very high pressure (bin 3).
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
        """Original small-room bidding rule set."""

        #
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

        # small room is same as the baseline
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

        bid = int(max(0, min(my_budget, raw_bid)))
        return bid, lead == 0

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
        """Original large-room bidding rule set."""

        # this might be different from the small room
        # because we want to be more aggressive in larger rooms where
        # price bands can be wider and there are more opponents to outbid,
        # but the core logic of counting paintings, estimating scarcity,
        # and calculating marginal gain remains the same.
        #
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

        # raw bid same as baseline but with the addition of the
        # regret term, which allows the bot to adjust its
        # bidding based on past outcomes.
        # The regret term is scaled by 0.8 to ensure that it has a significant
        # but not overwhelming influence on the bid,
        # allowing the bot to learn from its experiences while still considering
        # the other factors in its bidding strategy.
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

        # unlike the small room where we had a simpler need level
        # based on whether we were currently at the minimum count or not,
        # in the large room we have a more nuanced need level that considers whether we're at 0,
        # at the minimum, just above the minimum, or well above the minimum.
        # This allows us to tailor our bidding strategy more precisely based on how
        # critical this painting is for our scoring.
        if current_count == 0:
            need_level = 0
        elif current_count == min_count:
            need_level = 1
        elif current_count == min_count + 1:
            need_level = 2
        else:
            need_level = 3

        # if we have a strong need (need_level 0 or 1),
        # we want to be more aggressive in our bidding,
        # so we set a floor based on various conditions.
        # If we have a moderate need (need_level 2),
        # we want to ensure that we're bidding at least enough to stay competitive,
        # especially if there's pressure.
        # If we have a low need (need_level 3),
        # we want to be more conservative and not overbid,
        # so we set a cap based on the pace of our spending.
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

            # if we have a strong need and low pressure, we still want to set a reasonable floor to ensure that we're competitive, especially if the painting is scarce. If the painting is very scarce (scarcity > 1.3), we want to set a higher floor to reflect the increased competition for it, especially if there's any pressure or if we have a flat floor indicating that some opponents are in a certain price band. If there are many opponents (9 or more) and the painting is very scarce, we want to set an even higher floor to try to secure it.
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
        # if we have a moderate need, we want to ensure that we're bidding at least enough to stay competitive,
        # especially if there's pressure.
        # If there's no pressure, we can afford to be more conservative,
        # but if there is pressure, we want to make sure we're not underbidding
        # and losing out on a painting that could be important for our scoring.
        elif need_level == 2:
            raw_bid = max(raw_bid, pace if pressure_bin == 0 else max(pace, 10))
            if flat_floor >= 15 and scarcity > 1.25:
                raw_bid = max(raw_bid, 16)
        else:
            # if we have a low need, we want to be more conservative and not overbid,
            # so we set a cap based on the pace of our spending.
            raw_bid = min(raw_bid, max(0, pace * 0.8))

        # if volatile_exists is True, it means we've identified at least one opponent
        # who has won 3 or more paintings at an average price of 15 or more in the early rounds,
        # which suggests that there may be some aggressive bidding behavior in the room.
        # In this case, we want to be cautious with our bidding, especially if we're in the early rounds where such behavior is more likely to occur.
        # If we have a strong need (lead == 0), we set a cap on our bid to avoid getting into a bidding war that could deplete our budget too quickly.
        # If we don't have a strong need, we reduce our bid significantly to avoid overpaying in a volatile environment.
        if volatile_exists and current_round < 80:
            if lead == 0:
                cap = 11 if current_count == 0 or scarcity > 1.2 else 10
                if flat_floor >= 15 or pressure_bin >= 2:
                    cap = 16
                raw_bid = min(raw_bid, cap)
            else:
                raw_bid = min(raw_bid * 0.45, 7)

        # in both small and large rooms, we ensure that our bid is at least 0 and does not exceed our current budget, to avoid invalid bids. We also return whether we have a strong need for this painting (need_level 0 or 1), which can be used for regret updates in the next round.
        bid = int(max(0, min(my_budget, raw_bid)))
        return bid, need_level in (0, 1)

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
        """Dispatch to the original small-room or large-room strategy."""

        # my budget and unique_id are needed for both the regret update and the bidding logic, so we extract them here to avoid redundant lookups in the bidding methods.
        my_budget = my_bot_details["budget"]
        my_unique_id = my_bot_details["bot_unique_id"]

        # update regret based on the previous round's outcome before making the new bid, so that the bot can learn from narrow misses and adjust its bidding accordingly.
        self._update_regret(current_round, my_unique_id, winner_ids, amounts_paid)

        # if we have no budget left, we can't bid anything, so we return 0 immediately. We also update our last round and painting information to ensure that our regret updates will be accurate when we do have a budget again.
        if my_budget <= 0:
            self.last_round = current_round
            self.last_painting = current_painting
            self.last_bid = 0
            self.last_needed = False
            return 0

        # small room strategy is used when there are 5 or fewer bots, and large room strategy is used when there are more than 5 bots.
        # This is based on the original design choice that the dynamics of bidding and price pressure
        # can be quite different in smaller vs larger rooms, so it makes sense to have separate logic for each case.
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

        # update last round, painting, bid, and needed status for the next round's regret update, so that we have the necessary information to adjust our regret based on the outcome of this bid in the next round.
        self.last_round = current_round
        self.last_painting = current_painting
        self.last_bid = bid
        self.last_needed = needed
        return bid
