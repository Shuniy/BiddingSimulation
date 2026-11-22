"""
Baseline heuristic bot for the product-scoring auction.

Methodology:
1. Count the remaining paintings from `painting_order[current_round:]` to judge
   how scarce the current artist is.
2. Compare the current artist count to our minimum artist count because the
   score is the product of all four counts, so bottleneck artists matter most.
3. Scan opponents who also currently need the same artist to estimate local
   market pressure and any likely price floor.
4. Update a small regret signal from the previous round if we narrowly lost a
   needed painting or overpaid for a non-critical one.
5. Build a deterministic bid from budget pace, scarcity, marginal gain, and
   market pressure, then apply opening/endgame adjustments and safety caps.

Design choices:
- This bot is compact and readable.
- It focuses on balancing the collection rather than chasing surplus artists.
- The logic below is the original strategy; only explanatory comments/docs were
  added here.
"""

import math
from collections import Counter
from statistics import mean


class Bot(object):
    ARTISTS = ("Da Vinci", "Picasso", "Rembrandt", "Van Gogh")

    def __init__(self):
        self.name = "Collection Balancer"
        self.last_round = -1
        self.last_painting = None
        self.last_bid = 0
        self.last_needed = False
        self.regret = {artist: 0 for artist in self.ARTISTS}

    def _remaining_counts(self, painting_order, current_round):
        """Count how many paintings of each artist remain from this round onward."""

        return Counter(painting_order[current_round:])

    def _opponent_summary(
        self,
        bots,
        my_unique_id,
        current_painting,
        current_round,
        starting_budget,
        remaining_rounds,
    ):
        """
        Estimate local market pressure for the current artist.

        Only opponents who currently need this artist are treated as urgent
        competitors for price estimation.
        """

        market_pressure = []
        flat_floor = 0
        volatile_exists = False

        # for each bot, if they also need this painting,
        # then they are a direct competitor for it in this round,
        # so analyze their budget and pace to estimate how much pressure they might add to the price of this painting
        for bot in bots:
            if bot["bot_unique_id"] == my_unique_id:
                continue

            # each bot wins
            wins = sum(bot["paintings"].values())
            # calculate the average price they have paid per painting so far as a rough signal of how aggressively they might bid for this painting,
            avg_price = (starting_budget - bot["budget"]) / max(1, wins)
            # min_price is the cheapest painting they have won so far,
            #  which is a signal of how low they might be willing to go to win this painting,
            # especially if they need it badly and haven't won anything cheap yet
            opponent_min = min(bot["paintings"].values())
            # whether they need the current painting is determined by if their count of this artist is equal to their minimum count,
            # which means this artist is currently a bottleneck for them and winning this painting would directly
            # increase their score multiplier, so they have a strong incentive to compete for it
            needs_current = bot["paintings"][current_painting] == opponent_min

            # if they have won at least 3 paintings so far and their average price is at least 15,
            # that suggests they are aggressively pursuing their collection and might be a
            # volatile competitor who could drive up the price of this painting if they also need it,
            # especially in the early rounds before patterns have fully emerged,
            # so flag that a volatile competitor exists for safety capping later
            if wins >= 3 and avg_price >= 15 and current_round < 80:
                volatile_exists = True

            # if they don't need this painting, then they are not a direct competitor for it in this round,
            # so skip the rest of the analysis for this bot and move on to the next one
            if not needs_current:
                continue

            # if they need this painting and have won at least 5 paintings so far but their average price is between 8 and 12,
            # that suggests they have been steadily building their collection with moderate prices and
            # might be a consistent competitor who could set a price floor around 10 for this painting if they also need it,
            if wins >= 5 and 8 <= avg_price <= 12:
                flat_floor = 10

            # market pressure from this opponent is estimated as their remaining budget divided by the number of rounds they have left to spend it,
            # which is a rough signal of how much they might be willing to bid for this painting
            market_pressure.append(bot["budget"] / max(1, remaining_rounds))

        # market pressure is averaged across all opponents who need this painting to get a
        # general sense of how competitive the market might be for it in this round,
        market = mean(market_pressure) if market_pressure else 0.0
        return market, flat_floor, volatile_exists

    def _update_regret(self, current_round, my_unique_id, winner_ids, amounts_paid):
        """Track whether we narrowly missed a needed painting last round."""

        # base condition, if first round, not regret
        if (
            current_round == 0
            or self.last_painting is None
            or self.last_round != current_round - 1
            or len(winner_ids) < current_round
            or len(amounts_paid) < current_round
        ):
            return

        # now we have a valid last round,
        # so now we can measure regret

        # last round's winner and price
        winner = winner_ids[-1]
        amount_paid = amounts_paid[-1]

        # if we lost the painting we needed by a small margin, increase regret
        # if we won a painting we didn't need by overpaying, decrease regret
        if (
            self.last_needed
            and self.last_bid > 0
            and winner != my_unique_id
            and amount_paid <= self.last_bid + 2
        ):
            # we needed the last painting, we bid a positive amount,
            # but we lost it to another bot who didn't outbid us by much
            self.regret[self.last_painting] = min(
                self.regret[self.last_painting] + 1,
                3,
            )
        elif not self.last_needed and winner == my_unique_id and amount_paid >= 12:
            # if we didn't need the last painting, but we won it by paying a high price, decrease regret
            self.regret[self.last_painting] = max(
                self.regret[self.last_painting] - 1,
                0,
            )

    def _phase(self, counts, current_round):
        """Split the auction into opening, midgame, and endgame heuristics."""

        # conservatively treat any sold-out artist as a signal that we're in the opening phase where we should prioritize
        # completing sets,
        if min(counts.values()) == 0:
            return "opening"
        if current_round >= 150:
            return "endgame"
        return "midgame"

    def _midgame_bid(
        self,
        my_budget,
        remaining_rounds,
        lead,
        scarcity,
        marginal_gain,
        market,
        current_painting,
    ):
        """Core bid formula used before later phase/floor adjustments."""

        # base is my average budget per round for the rest of the auction,
        # which is a starting point for how much I can afford to bid for this painting while pacing my budget,
        base = my_budget / remaining_rounds

        # raw bid is calculated from the base budget pace,
        # adjusted by a combination of marginal gain from this painting, local lead, scarcity, and market pressure,
        raw = (
            base
            * (
                0.8
                + 7.5 * marginal_gain
                - 0.25 * max(0, lead)
                + 0.25 * max(0.0, scarcity - 1.0)
            )
            + 0.7 * market
        )
        return raw

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
        """Return the original deterministic heuristic bid."""

        # my unique id is needed for regret tracking and opponent summary, so extract it once here
        my_unique_id = my_bot_details["bot_unique_id"]
        # update regret from the previous round's outcome before calculating the new bid
        self._update_regret(current_round, my_unique_id, winner_ids, amounts_paid)

        # my budget is the main constraint on bidding, so extract it once here
        my_budget = my_bot_details["budget"]

        # if my budget is already depleted, I can't bid anything, so return early and skip all the logic below
        if my_budget <= 0:
            self.last_round = current_round
            self.last_painting = current_painting
            self.last_bid = 0
            self.last_needed = False
            return 0

        # now calculate how badly we want that painting based on our current collection,
        # the remaining paintings, and the market context

        # total counts of each artist in my collection so far,
        # which is the main state variable for bidding decisions
        counts = my_bot_details["paintings"]
        # min_count is the bottleneck artist count,
        # which determines the score multiplier,
        # so it's a key reference point for how urgently I need the current painting
        min_count = min(counts.values())
        # current_count is how many paintings of the current artist I have,
        # which is directly relevant to the score gain from winning this painting and also my local lead
        current_count = counts[current_painting]
        # lead is how many more paintings of the current artist I have than my bottleneck,
        lead = current_count - min_count

        # remaining_counts is how many paintings of each artist remain in the auction,
        remaining_counts = self._remaining_counts(painting_order, current_round)
        # remaining_rounds is how many paintings remain in the auction,
        # which is relevant for pacing my budget and also judging scarcity,
        remaining_rounds = max(1, round_limit - current_round)
        # remaining_current is how many paintings of the current artist remain in the auction,
        # which is directly relevant to how scarce this artist is and how likely
        # I am to get more chances to buy it later, so it's a key variable for my bid calculation,
        remaining_current = max(1, remaining_counts[current_painting])
        # scarcity is the ratio of remaining rounds to remaining paintings of this artist,
        scarcity = remaining_rounds / remaining_current

        # The score is a product, so a smoothed log-product gain is used as the
        # value proxy for one more copy of the current artist.
        # The "+1" smoothing means the first copy is worth more than subsequent ones,
        # which encourages completing a set and also reflects the diminishing returns of
        # surplus copies.
        marginal_gain = math.log(current_count + 2) - math.log(current_count + 1)

        # contextual market summary for this painting based on opponents who also need it,
        market, flat_floor, volatile_exists = self._opponent_summary(
            bots=bots,
            my_unique_id=my_unique_id,
            current_painting=current_painting,
            current_round=current_round,
            starting_budget=starting_budget,
            remaining_rounds=remaining_rounds,
        )

        # phase is determined by whether any artist is sold out
        # (opening), or if we're in the last rounds (endgame), or otherwise (midgame),
        phase = self._phase(counts, current_round)
        # midgame_bid is the core deterministic bid before applying any phase-specific adjustments or safety caps,
        raw_bid = self._midgame_bid(
            my_budget=my_budget,
            remaining_rounds=remaining_rounds,
            lead=lead,
            scarcity=scarcity,
            marginal_gain=marginal_gain,
            market=market,
            current_painting=current_painting,
        )

        # round and scarcity adjustments:
        if phase == "opening":
            # round 1 adjustment: be more aggressive for the first painting since
            # it's the only chance to get it and set the tone for the auction,
            if current_count == 0:
                raw_bid += 1
        elif phase == "endgame":
            # if we don't have any of this artist yet, be more aggressive since there are no more chances to get it later,
            if lead == 0:
                raw_bid += 1
            # if this artist is very scarce, be more aggressive since the price is likely to go up and
            # there are few chances to get it later,
            if scarcity > 1.2:
                raw_bid += 1

        # if we have no paintings of this artist,
        #  we need it for our score multiplier and it's likely to be more contested, so be more aggressive,
        if current_count == 0:
            #  raise the bid floor to at least 10 to be competitive for this painting, especially if the market summary suggests a flat floor or if scarcity is high or we're in the endgame where there are few chances to get it later,
            raw_bid = max(raw_bid, max(flat_floor, 10))
            # if scarcity is high or we're in the endgame,
            # be even more aggressive since the price is likely to go up and there are few chances to get it later,
            if scarcity > 1.2 or current_round > 150:
                raw_bid = max(raw_bid, 11)
        # if we have some paintings of this artist but it's currently our bottleneck and the market summary suggests a flat floor,
        # be more aggressive to try to win this painting and maintain our lead,
        # flat floor is a signal that there is consistent competition for this painting at a certain price point,
        # so if we're currently tied for the lead on this artist,
        # we want to be more aggressive to try to win this painting and break the tie,
        # especially since having more of this artist would increase our score multiplier and potentially put us in the lead overall,
        elif lead == 0 and flat_floor:
            # even if we have some of this artist, if we are currently tied for the lead and the market summary suggests a flat floor, be more aggressive to try to win this painting and break the tie,
            raw_bid = max(raw_bid, 10)

        # if a volatile competitor exists for this painting and we're in the early rounds where patterns are still emerging,
        # apply a safety cap to avoid overbidding in a potentially volatile market,
        # especially if we're not currently leading on this artist or if it's not our bottleneck,
        if volatile_exists and current_round < 80:
            # if we're not currently leading on this artist,
            # apply a safety cap to avoid overbidding in a potentially volatile market,
            if lead == 0:
                cap = 11 if current_count == 0 or scarcity > 1.2 else 10
                raw_bid = min(raw_bid, cap)
            else:
                # else if we're currently leading on this artist,
                # we can afford to be a bit more aggressive since winning this painting would increase our lead
                # and score multiplier, but still apply a safety cap to avoid overbidding in a potentially volatile market,
                raw_bid = min(raw_bid * 0.45, 7)

        # bid is the final amount we decide to bid for this painting,
        # which is the raw bid adjusted by all the heuristics above,
        # but also capped to be within our remaining budget and not negative,
        bid = int(max(0, min(my_budget, raw_bid)))

        # update last round info for regret tracking in the next round,
        self.last_round = current_round
        self.last_painting = current_painting
        self.last_bid = bid
        self.last_needed = lead == 0

        return bid
