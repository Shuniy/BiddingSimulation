import math
from bisect import insort
from collections import Counter, deque
from statistics import mean, median, stdev


class Bot(object):
    def __init__(self):
        self.name = "Price Profile Bidder"
        self.artists = ["Da Vinci", "Picasso", "Rembrandt", "Van Gogh"]
        self.artist_set = set(self.artists)

        # Regret memory
        self.type_bid_adjustment = {artist: 0.0 for artist in self.artists}
        self.reset_game_state()

    def reset_game_state(self):
        # reset game state
        self.game_signature = None
        self.my_id = None
        self.last_processed_history_len = 0
        self.remaining_supply_by_round = []
        self.future_window_supply_by_round = {}
        self.recent_global_prices = deque(maxlen=15)
        self.recent_prices_by_artist = {
            artist: deque(maxlen=15) for artist in self.artists
        }
        self.global_auction_stats = self.new_price_stats()
        self.artist_auction_stats = {
            artist: self.new_price_stats() for artist in self.artists
        }
        self.opponent_history = {}
        self.recent_auction_window = deque(maxlen=20)
        self.ideal_budget_per_round = 0
        self.my_bids = []
        self.last_needed = False

    def new_price_stats(self):
        return {
            "count": 0,
            "sum": 0.0,
            "sorted_prices": [],
            "mean": 0.0,
            "median": 0.0,
            "std_dev": 0.0,
        }

    def update_price_stats(self, stats, paid):
        paid_value = float(paid)
        stats["count"] += 1
        stats["sum"] += paid_value
        insort(stats["sorted_prices"], int(paid))

        sorted_prices = stats["sorted_prices"]
        count = len(sorted_prices)
        trim = int(count * 0.15)
        trimmed_prices = (
            sorted_prices[trim : count - trim]
            if count - 2 * trim >= 1
            else sorted_prices
        )

        trimmed_count = len(trimmed_prices)
        trimmed_sum = float(sum(trimmed_prices))
        stats["mean"] = trimmed_sum / max(1, trimmed_count)
        stats["median"] = median(trimmed_prices)
        stats["std_dev"] = stdev(trimmed_prices) if len(trimmed_prices) >= 2 else 0

    def create_game_state_cache(self, painting_order, my_bot_details):
        game_paintings = tuple(painting_order)
        if self.game_signature != game_paintings:
            self.reset_game_state()
            self.game_signature = game_paintings
            self.build_caches(painting_order)

        normalized_me = self.normalize_bot(my_bot_details)
        self.my_id = normalized_me["bot_unique_id"]
        return normalized_me

    def build_caches(self, painting_order):
        round_count = len(painting_order)
        self.remaining_supply_by_round = [
            {artist: 0 for artist in self.artists} for _ in range(round_count + 1)
        ]

        running_counts = {artist: 0 for artist in self.artists}
        for round_index in range(round_count - 1, -1, -1):
            artist = painting_order[round_index]
            if artist in self.artist_set:
                running_counts[artist] += 1
            self.remaining_supply_by_round[round_index] = dict(running_counts)

        self.future_window_supply_by_round = {}
        for window in (8, 20, 50):
            window_counts = []
            for round_index in range(round_count + 1):
                counts = {artist: 0 for artist in self.artists}
                future_end = min(round_count, round_index + window)
                for future_artist in painting_order[round_index:future_end]:
                    if future_artist in self.artist_set:
                        counts[future_artist] += 1
                window_counts.append(counts)
            self.future_window_supply_by_round[window] = window_counts

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
        normalized_me = self.create_game_state_cache(painting_order, my_bot_details)

        # state representation
        state = self.build_state(
            current_round=current_round,
            bots=bots,
            round_limit=round_limit,
            starting_budget=starting_budget,
            painting_order=painting_order,
            current_painting=current_painting,
            winner_ids=winner_ids,
            amounts_paid=amounts_paid,
            my_bot=normalized_me,
        )

        # if we are out of budget, we can't bid
        if state["my_budget"] <= 0:
            self.last_needed = False
            return 0

        # ideal budget per round to spend
        self.ideal_budget_per_round = state["my_budget"] / max(
            1, state["remaining_rounds"]
        )

        # update regret learning based on past outcomes
        self.update_regret(state)
        # extract features to inform our bid decision
        features = self.extract_features(state)
        # decide on a bid amount based on the state and features
        bid, needed = self.decide_bid(state, features)
        final_bid = int(max(0, min(state["my_budget"], math.ceil(bid))))
        self.my_bids.append(final_bid)
        self.last_needed = needed
        return final_bid

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
        my_bot,
    ):
        normalized_bots = [self.normalize_bot(bot) for bot in bots]
        my_id = my_bot["bot_unique_id"]
        remaining_rounds = max(1, int(round_limit) - int(current_round))

        return {
            "current_round": int(current_round),
            "round_limit": int(round_limit),
            "remaining_rounds": remaining_rounds,
            "progress": int(current_round) / max(1, int(round_limit)),
            "starting_budget": int(starting_budget),
            "painting_order": painting_order,
            "current_painting": str(current_painting),
            "winner_ids": winner_ids,
            "amounts_paid": amounts_paid,
            "my_bot": my_bot,
            "my_id": my_id,
            "my_budget": my_bot["budget"],
            "pace": my_bot["budget"] / remaining_rounds,
            "my_score": my_bot["score"],
            "my_paintings": my_bot["paintings"],
            "opponents": [
                bot for bot in normalized_bots if bot["bot_unique_id"] != my_id
            ],
        }

    def normalize_bot(self, bot):
        # normalize bot details to ensure consistent data types and structures, which can help avoid issues with unexpected formats and make it easier to work with the bot data in our state representation and logic -
        return {
            "bot_name": bot["bot_name"],
            "bot_unique_id": bot["bot_unique_id"],
            "paintings": self.normalize_paintings(bot["paintings"]),
            "budget": int(bot["budget"]),
            "score": int(bot["score"]),
        }

    def normalize_paintings(self, paintings):
        # normalize paintings to ensure we have integer counts for each artist, which can help avoid issues with unexpected formats and make it easier to compute features and make decisions based on the paintings data -
        return {artist: int(paintings.get(artist, 0)) for artist in self.artists}

    def percentile(self, values, q):
        if not values:
            return 0

        values = sorted(values)
        n = len(values)

        idx = q * (n - 1)
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))

        if lo == hi:
            return values[lo]

        frac = idx - lo
        return values[lo] * (1 - frac) + values[hi] * frac

    def update_regret(self, state):
        # simple heuristic: if we lost a painting for a low price, increase our bid adjustment for that artist;
        # if we won but paid a high price, decrease it

        # winner_ids, amounts_paid, and painting_order should all be the same length, representing the history of auctions so far
        winner_ids = state["winner_ids"]
        amounts_paid = state["amounts_paid"]
        painting_order = state["painting_order"]
        my_id = state["my_id"]

        # history_len represents how many completed auctions we have data for -
        # we only want to process new ones since the last time we updated
        history_len = min(len(winner_ids), len(amounts_paid), len(painting_order))

        # history_len should never be less than last_processed_history_len, but we check just in case to avoid accidentally processing the same auction multiple times
        if history_len <= self.last_processed_history_len:
            return

        for i in range(self.last_processed_history_len, history_len):
            artist = painting_order[i]
            winner_id = winner_ids[i]
            paid = int(amounts_paid[i])

            if artist not in self.artist_set:
                continue

            # if we lost this auction, we want to increase our bid adjustment for this artist to try to win it next time;
            if winner_id != my_id:
                self.learn_from_loss(artist, paid)
            # if we won this auction, we want to decrease our bid adjustment for this artist to try to avoid overpaying next time
            else:
                self.learn_from_win(artist, paid)

            if self.last_needed:
                self.type_bid_adjustment[artist] += 0.03

            self.type_bid_adjustment[artist] = max(
                -2.5, min(4.0, self.type_bid_adjustment[artist])
            )

            self.recent_global_prices.append(paid)
            self.recent_prices_by_artist[artist].append(paid)
            self.update_price_stats(self.global_auction_stats, paid)
            self.update_price_stats(self.artist_auction_stats[artist], paid)
            self.update_opponent_history(winner_id, artist, paid)

        self.last_processed_history_len = history_len

    def empty_opponent_stats(self):
        # empty opponent stats structure to initialize the history for a new opponent when we first encounter them in the auction history, which allows us to start tracking their wins, prices paid, and focus on different artists from that point onward to inform our opponent modelling and threat assessment in future auctions - we track total wins, wins by artist, price sums and counts by artist for market price estimation, and recent wins by artist to capture their current focus and aggression towards different artists
        return {
            "total_wins": 0,
            "wins_by_artist": {artist: 0 for artist in self.artists},
            "price_sum_by_artist": {artist: 0 for artist in self.artists},
            "price_count_by_artist": {artist: 0 for artist in self.artists},
            "recent_wins_by_artist": {artist: 0 for artist in self.artists},
        }

    def update_opponent_history(self, winner_id, artist, paid):
        history = self.opponent_history.setdefault(
            winner_id, self.empty_opponent_stats()
        )
        history["total_wins"] += 1
        history["wins_by_artist"][artist] += 1
        history["price_sum_by_artist"][artist] += paid
        history["price_count_by_artist"][artist] += 1

        if len(self.recent_auction_window) == self.recent_auction_window.maxlen:
            old_winner_id, old_artist = self.recent_auction_window.popleft()
            old_history = self.opponent_history.get(old_winner_id)
            if old_history and old_artist in self.artist_set:
                old_history["recent_wins_by_artist"][old_artist] = max(
                    0, old_history["recent_wins_by_artist"][old_artist] - 1
                )

        self.recent_auction_window.append((winner_id, artist))
        history["recent_wins_by_artist"][artist] += 1

    def learn_from_loss(self, artist, paid):
        # learn from losing an auction for a painting of this artist - if we lost for a low price,
        # we likely underbid and should increase our bid adjustment more;
        # if we lost for a high price, we were close but still lost,
        # so we should increase our bid adjustment but not as much;
        # if we lost for a very high price, we might have been too aggressive and
        # should be careful about increasing our bid adjustment too much
        median_price = self.artist_auction_stats[artist]["median"]
        std_price = self.artist_auction_stats[artist]["std_dev"]
        my_loss_gap = paid - self.my_bids[-1] if self.my_bids else paid

        if my_loss_gap <= 1:
            self.type_bid_adjustment[artist] += 0.14
        elif my_loss_gap <= 3:
            self.type_bid_adjustment[artist] += 0.08
        elif my_loss_gap <= 6:
            self.type_bid_adjustment[artist] += 0.04

        if paid <= 10:
            self.type_bid_adjustment[artist] += 0.14
        elif paid <= 15:
            self.type_bid_adjustment[artist] += 0.08
        elif paid <= 25:
            self.type_bid_adjustment[artist] += 0.03
        elif paid > median_price:
            self.type_bid_adjustment[artist] -= 0.02
        else:
            self.type_bid_adjustment[artist] += 0.01

        if std_price >= 5 and my_loss_gap <= 3:
            self.type_bid_adjustment[artist] += 0.03

    def learn_from_win(self, artist, paid):
        # learn from winning an auction for a painting of this artist -
        # if we won but paid a high price,
        # we likely overbid and should decrease our bid adjustment to try to avoid overpaying next time;
        # if we won and paid a moderate price, we might be in a good range
        # but could still try to be a bit more efficient by decreasing our bid adjustment slightly;
        # if we won and paid a low price,
        # we might have been able to bid even less and still win,
        # so we should decrease our bid adjustment a bit more to try to find that more efficient winning bid next
        median_price = self.artist_auction_stats[artist]["median"]
        std_price = self.artist_auction_stats[artist]["std_dev"]
        if paid >= median_price:
            self.type_bid_adjustment[artist] -= 0.14
        if paid >= 25:
            self.type_bid_adjustment[artist] -= 0.12
        elif paid >= 18:
            self.type_bid_adjustment[artist] -= 0.07
        elif paid <= 10:
            self.type_bid_adjustment[artist] += 0.03

        if std_price <= 3 and paid > 0:
            self.type_bid_adjustment[artist] -= 0.02

    def extract_features(self, state):
        # extract various features from the current state to inform our bid decision, such as:
        # - how many paintings of the current artist are still available in the future (supply/ scarcity)
        # - how many paintings of the current artist we already have and how much would it increase our score (value/ marginal gain)
        # - what is the current market price for paintings of this artist based on recent auction history (market price estimation)
        # - how strong are our opponents' needs and budgets for this painting based on their past behaviour (opponent modelling)
        current_painting = state["current_painting"]
        my_paintings = state["my_paintings"]
        current_round = state["current_round"]

        # get supply/scarcity features
        remaining_supply = self.find_remaining_supply(current_round)
        # get supply in near future windows to capture local urgency beyond overall scarcity
        future_window_supply = self.find_future_window_supply(
            current_round, window_sizes=[8, 20, 50]
        )

        current_score = state["my_score"]
        # marginal gain if we acquire this painting - how much would our score increase if we win this painting,
        # which captures the value of this painting to us based on our current collection
        marginal_gain = self.find_marginal_product_gain(
            my_paintings, current_painting, current_score
        )

        # market price estimation based on recent auction history for this artist and overall, which can help us understand the price we might have to pay to acquire this painting
        market_price, volatile_exists = self.find_estimated_market_price(
            state, current_painting=current_painting
        )

        # opponent modelling to assess the threat level of our opponents
        # for this painting based on their past wins, prices paid,
        # and focus on this artist, which can help us understand
        # how competitive the auction for this painting might be and how much pressure
        # we might face from opponents who really want it
        opponent_model = self.model_opponents(state, market_price)

        # scarcity score that combines overall remaining supply and local urgency based on future window supply to capture both how scarce this painting is overall and how urgently we might need to acquire it based on the near future supply, which can help inform how much we should value this painting in our bid decision
        scarcity_score = self.find_scarcity_score(
            state=state,
            current_painting=current_painting,
            remaining_supply=remaining_supply,
            future_window_supply=future_window_supply,
        )

        # pressure to balance our collection based on
        # how many paintings of this artist we already have compared to our least collected artist,
        # which can help us understand how much we might want to acquire this painting to maintain a balanced collection
        # and avoid having a weak category that could limit our score
        balance_pressure = self.find_balance_pressure(
            my_paintings=my_paintings, current_painting=current_painting
        )

        # learnt regret adjustment for this artist based on our past wins/losses and prices paid, which can help us adapt our bidding strategy for this artist over time based on our experience in the auctions so far
        learned_adjustment = self.type_bid_adjustment.get(current_painting, 0.0)

        # compute endgame state based on our progress in the game, our budget, our collection, and the remaining supply of this artist, which can help us understand how urgently we might need to acquire this painting and how much risk we might want to take in our bid decision as we approach the endgame where we need to convert our budget into score efficiently to maximize our chances of winning
        endgame_state = self.find_endgame_state(
            state=state, remaining_supply=remaining_supply
        )

        return {
            "remaining_supply": remaining_supply,
            "future_window_supply": future_window_supply,
            "current_score": current_score,
            "marginal_gain": marginal_gain,
            "market_price": market_price,
            "artist_stats": self.artist_auction_stats[current_painting],
            "global_stats": self.global_auction_stats,
            "volatile_exists": volatile_exists,
            "opponent_model": opponent_model,
            "scarcity_score": scarcity_score,
            "balance_pressure": balance_pressure,
            "learned_adjustment": learned_adjustment,
            "endgame_state": endgame_state,
        }

    def find_remaining_supply(self, current_round):
        round_index = min(current_round, len(self.remaining_supply_by_round) - 1)
        return self.remaining_supply_by_round[round_index]

    def find_future_window_supply(self, current_round, window_sizes):
        result = {}
        for window in window_sizes:
            cached_window = self.future_window_supply_by_round.get(window)
            if cached_window:
                round_index = min(current_round, len(cached_window) - 1)
                result[window] = cached_window[round_index]
            else:
                result[window] = {artist: 0 for artist in self.artists}
        return result

    def find_scarcity_score(
        self, state, current_painting, remaining_supply, future_window_supply
    ):
        # combine overall remaining supply and local urgency based on future window supply to compute a scarcity score for this painting, which can help us understand how scarce this painting is and how urgently we might need to acquire it based on the near future supply -
        total_remaining = remaining_supply[current_painting]
        near_8 = future_window_supply[8][current_painting]
        near_20 = future_window_supply[20][current_painting]

        if total_remaining <= 0:
            return 1.0

        scarcity_ratio = state["remaining_rounds"] / total_remaining
        overall_scarcity = min(0.55, 0.18 * max(0.0, scarcity_ratio - 1.0))
        local_urgency = 0.0

        if near_8 == 0:
            local_urgency += 0.30
        elif near_8 == 1:
            local_urgency += 0.14

        if near_20 <= 1:
            local_urgency += 0.18
        elif near_20 <= 3:
            local_urgency += 0.08

        if state["my_paintings"][current_painting] == min(
            state["my_paintings"].values()
        ):
            local_urgency += 0.05

        return min(1.0, overall_scarcity + local_urgency)

    def find_product_score(self, paintings):
        # get our current score based on the paintings we have - in this game, the score is the product of the counts of each artist,
        score = 1
        for artist in self.artists:
            score *= max(0, int(paintings.get(artist, 0)))
        return score

    def find_marginal_product_gain(
        self, my_paintings, current_painting, current_score=None
    ):
        # get marginal gain in our score if we acquire this painting, which can help us understand the value of this painting to us based on our current collection -
        old_score = (
            self.find_product_score(my_paintings)
            if current_score is None
            else int(current_score)
        )
        current_count = my_paintings[current_painting]
        if current_count <= 0:
            other_product = 1
            for artist in self.artists:
                if artist != current_painting:
                    other_product *= max(0, int(my_paintings.get(artist, 0)))
            new_score = other_product
        else:
            new_score = old_score * (current_count + 1) / current_count
        count_gain = math.log(current_count + 2) - math.log(current_count + 1)
        score_gain = math.log(new_score + 1) - math.log(old_score + 1)
        return max(score_gain, count_gain)

    def find_balance_pressure(self, my_paintings, current_painting):
        # compute pressure to acquire this painting to maintain a balanced collection based on how many paintings of this artist we already have compared to our least collected artist - if we have fewer paintings of this artist compared to our least collected artist, we might want to acquire this painting to avoid having a weak category that could limit our score, so the pressure is higher; if we already have more paintings of this artist compared to our least collected artist, the pressure is lower since acquiring more of this artist doesn't help balance our collection as much
        current_count = my_paintings[current_painting]
        min_count = min(my_paintings.values())

        if current_count == min_count:
            return 1.0
        elif current_count == min_count + 1:
            return 0.6
        elif current_count == min_count + 2:
            return 0.3
        return 0.1

    def find_estimated_market_price(self, state, current_painting):
        if not self.recent_global_prices:
            return min(1, self.ideal_budget_per_round), False

        market_pressure = []
        volatile_exists = False
        for bot in state["opponents"]:
            if bot["bot_unique_id"] == self.my_id:
                continue
            wins = sum(bot["paintings"].values())
            avg_price = (state["starting_budget"] - bot["budget"]) / max(1, wins)
            opponent_min = min(bot["paintings"].values())
            needs_current = bot["paintings"][current_painting] == opponent_min
            if wins >= 3 and avg_price >= 15 and state["current_round"] < 80:
                volatile_exists = True

            if not needs_current:
                continue

            market_pressure.append(bot["budget"] / max(1, state["remaining_rounds"]))

        market_pressure = median(market_pressure) if market_pressure else 0.0
        artist_stats = self.artist_auction_stats[current_painting]
        global_stats = self.global_auction_stats

        artist_count = artist_stats["count"]
        artist_median = artist_stats["median"]
        artist_mean = artist_stats["mean"]
        artist_std = artist_stats["std_dev"]
        global_median = global_stats["median"]
        global_mean = global_stats["mean"]
        global_std = global_stats["std_dev"]

        if artist_count == 0:
            blended = max(
                self.ideal_budget_per_round,
                0.80 * global_median + 0.10 * global_mean + 0.10 * market_pressure,
            )
            if volatile_exists:
                blended += 0.12 * global_std
            return max(1, int(blended)), volatile_exists

        artist_anchor = 0.80 * artist_median + 0.20 * artist_mean
        global_anchor = 0.85 * global_median + 0.15 * global_mean
        blended = 0.80 * artist_anchor + 0.10 * global_anchor + 0.10 * market_pressure

        if volatile_exists:
            blended += 0.50 * max(global_std, artist_std)

        return max(1, int(blended)), volatile_exists

    def find_robust_median(self, values):
        # if we have no values, we can return a default estimate of 1 to avoid issues with empty data
        if not values:
            return 1

        # sort the values and take the middle one as a simple median, which gives us a central estimate of the typical price while being more robust to outliers than the mean
        vals = sorted(int(v) for v in values)

        # if we have 2 or fewer values, we can just return the middle one (or the only one) as the median, which allows us to still have a reasonable estimate even with very limited data without trying to do any trimming that wouldn't make sense with such a small sample size
        if len(vals) <= 2:
            return vals[len(vals) // 2]

        # if we have more than 2 values,
        # we can trim the top and bottom 15% to reduce the impact of outliers
        # and get a more robust median estimate,
        # which helps ensure that our market price estimation
        # is not overly influenced by anomalously high or low prices in the history
        trim = int(len(vals) * 0.15)
        trimmed = vals[trim : len(vals) - trim] if len(vals) - 2 * trim >= 1 else vals

        return trimmed[len(trimmed) // 2]

    def find_opponent_need(
        self, opponent_paintings, current_painting, my_current_count
    ):
        # compute how much an opponent might need the current painting based on how many paintings of this artist they already have compared to us -
        opp_count = opponent_paintings[current_painting]
        base_need = 1.0 / (opp_count + 1)
        if opp_count < my_current_count:
            base_need += 0.15
        return min(1.0, base_need)

    def find_budget_strength(self, opponent_budget, starting_budget):
        # compute how strong an opponent's budget is relative to the starting budget, which can help us understand how much financial capacity they have left to compete for this painting and how aggressive they might be able to be in their bidding -
        return min(1.0, opponent_budget / max(1, starting_budget))

    def find_score_pressure(self, opponent_score, my_score):
        # compute score pressure based on the opponent's current score compared to ours, which can help us understand how motivated they might be to acquire this painting to catch up or maintain their lead in terms of score -
        if opponent_score < my_score:
            gap_ratio = (my_score - opponent_score) / max(1, my_score)
            return min(1.0, 0.4 + gap_ratio)
        return 0.4

    def find_artist_aggression(
        self, opp_history, current_painting, total_rounds_played
    ):
        # compute artist aggression based on the opponent's past wins and focus on this artist, which can help us understand how aggressive they might be in bidding for this painting based on their demonstrated interest and success with this artist in the past -
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

    def find_price_aggression(self, opp_history, current_painting, market_price):
        # compute price aggression based on the opponent's past prices paid for this artist compared to the current market price, which can help us understand how aggressive they might be in their bidding for this painting based on their demonstrated willingness to pay for paintings of this artist in the past -
        if not opp_history:
            return 0.0

        price_count = opp_history["price_count_by_artist"][current_painting]
        if price_count <= 0 or market_price <= 0:
            return 0.0

        avg_price = opp_history["price_sum_by_artist"][current_painting] / price_count
        ratio = avg_price / market_price
        return min(1.0, ratio / 2.0)

    def combine_opponent_threat(
        self,
        opp_need,
        budget_strength,
        score_pressure,
        artist_aggression,
        price_aggression,
    ):
        # combine the various factors to compute an overall threat level for this opponent in the auction for the current painting, which can help us understand how competitive the auction might be and how much pressure we might face from this opponent who could really want this painting
        threat = (
            0.30 * opp_need
            + 0.25 * budget_strength
            + 0.15 * score_pressure
            + 0.20 * artist_aggression
            + 0.10 * price_aggression
        )
        return min(1.0, threat)

    def model_opponents(self, state, market_price):
        # opponent modelling to assess the threat level of our opponents for the current painting based on their past wins, prices paid, and focus on this artist -
        current_painting = state["current_painting"]
        opponents = state["opponents"]
        starting_budget = state["starting_budget"]
        my_score = state["my_score"]
        my_paintings = state["my_paintings"]
        amounts_paid = state["amounts_paid"]

        my_current_count = my_paintings[current_painting]
        total_rounds_played = len(amounts_paid)

        opponent_profiles = []
        threat_values = []

        # for each opponent, compute various features of their behaviour and situation to assess how much of a threat they might be in the auction for the current painting -
        for opp in opponents:
            opp_id = opp["bot_unique_id"]
            opp_hist = self.opponent_history.get(opp_id)

            # compute opponent's need for this painting based on how many paintings of this artist they already have compared to us, which gives us a sense of how much they might want this painting and how competitive the auction might be
            opp_need = self.find_opponent_need(
                opponent_paintings=opp["paintings"],
                current_painting=current_painting,
                my_current_count=my_current_count,
            )

            # compute opponent's budget strength relative to the starting budget, which helps us understand how much financial capacity they have left to compete for this painting and how aggressive they might be able to be in their bidding
            budget_strength = self.find_budget_strength(
                opponent_budget=opp["budget"], starting_budget=starting_budget
            )

            # compute score pressure based on the opponent's current score compared to ours, which can help us understand how motivated they might be to acquire this painting to catch up or maintain their lead in terms of score
            score_pressure = self.find_score_pressure(
                opponent_score=opp["score"], my_score=my_score
            )

            # compute artist aggression based on the opponent's past wins and focus on this artist, which can help us understand how aggressive they might be in bidding for this painting based on their demonstrated interest and success with this artist in the past
            artist_aggression = self.find_artist_aggression(
                opp_history=opp_hist,
                current_painting=current_painting,
                total_rounds_played=total_rounds_played,
            )

            # compute price aggression based on the opponent's past prices paid for this artist compared to the current market price, which can help us understand how aggressive they might be in their bidding for this painting based on their demonstrated willingness to pay for paintings of this artist in the past
            price_aggression = self.find_price_aggression(
                opp_history=opp_hist,
                current_painting=current_painting,
                market_price=market_price,
            )

            # threat is a combined measure of how much of a competitive threat this opponent might be in the auction for the current painting based on their need for it, their budget strength, the score pressure they are under, and their demonstrated aggression in terms of both their focus on this artist and their willingness to pay for it in the past
            threat = self.combine_opponent_threat(
                opp_need=opp_need,
                budget_strength=budget_strength,
                score_pressure=score_pressure,
                artist_aggression=artist_aggression,
                price_aggression=price_aggression,
            )

            # create a profile for this opponent with all the computed features and the overall threat level, which can be useful for analysis and understanding of our opponents as well as for debugging and improving our opponent modelling over time
            profile = {
                "bot_name": opp["bot_name"],
                "bot_unique_id": opp["bot_unique_id"],
                "opp_need": opp_need,
                "budget_strength": budget_strength,
                "score_pressure": score_pressure,
                "artist_aggression": artist_aggression,
                "price_aggression": price_aggression,
                "threat": threat,
            }

            opponent_profiles.append(profile)
            threat_values.append(threat)

        # if we have threat values for our opponents, we can compute the strongest threat, the average threat, and a total pressure score that combines these factors to give us an overall sense of how competitive the auction for this painting might be based on our opponents' behaviour and situation - the strongest threat captures the most competitive opponent we might face, while the average threat gives us a sense of the overall competitive landscape, and the total pressure score combines these to help inform our bidding strategy in terms of how much pressure we might be under from our opponents in this auction
        if threat_values:
            strongest_threat = max(threat_values)
            average_threat = sum(threat_values) / len(threat_values)
            total_pressure = 0.65 * strongest_threat + 0.35 * average_threat
        else:
            strongest_threat = 0.0
            average_threat = 0.0
            total_pressure = 0.0

        return {
            "profiles": opponent_profiles,
            "strongest_threat": strongest_threat,
            "average_threat": average_threat,
            "total_pressure": total_pressure,
        }

    def find_endgame_state(self, state, remaining_supply):
        progress = state["progress"]
        remaining_rounds = state["remaining_rounds"]
        my_budget = state["my_budget"]
        my_paintings = state["my_paintings"]
        current_painting = state["current_painting"]

        min_count = min(my_paintings.values())
        current_count = my_paintings[current_painting]
        budget_per_remaining_round = my_budget / max(1, remaining_rounds)
        supply_left = remaining_supply[current_painting]

        is_late_game = progress >= 0.75
        is_deep_endgame = progress >= 0.90 or remaining_rounds <= 15
        is_weak_category = current_count == min_count
        is_near_weak_category = current_count == min_count + 1
        scarce_now = supply_left <= 5
        very_scarce_now = supply_left <= 2
        rich_for_remaining_time = budget_per_remaining_round >= 8
        very_rich_for_remaining_time = budget_per_remaining_round >= 15

        urgency = 0.0
        if is_late_game:
            urgency += 0.25
        if is_deep_endgame:
            urgency += 0.25
        if is_weak_category:
            urgency += 0.25
        elif is_near_weak_category:
            urgency += 0.12
        if scarce_now:
            urgency += 0.15
        if very_scarce_now:
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
            "is_late_game": is_late_game,
            "is_deep_endgame": is_deep_endgame,
            "is_weak_category": is_weak_category,
            "is_near_weak_category": is_near_weak_category,
            "scarce_now": scarce_now,
            "very_scarce_now": very_scarce_now,
            "rich_for_remaining_time": rich_for_remaining_time,
            "very_rich_for_remaining_time": very_rich_for_remaining_time,
            "budget_per_remaining_round": budget_per_remaining_round,
        }

    def find_price_stats(self, current_painting, artist_stats, global_stats):
        artist_recent = list(self.recent_prices_by_artist[current_painting])[-10:]
        global_recent = list(self.recent_global_prices)[-20:]
        sample = (
            artist_recent if len(artist_recent) >= 4 else artist_recent + global_recent
        )

        if not sample:
            fallback = max(1, int(round(self.ideal_budget_per_round)))
            return {
                "mode_price": fallback,
                "mode_strength": 0.0,
                "median_price": fallback,
                "mean_price": fallback,
                "std_dev": 0.0,
                "lower_anchor": fallback,
                "reference_price": fallback,
                "stable_mode": False,
                "percentile_50": fallback,
                "percentile_75": fallback,
                "percentile_25": fallback,
                "percentile_90": fallback,
            }

        bucketed = [int(round(price)) for price in sample]
        p50 = self.percentile(bucketed, 0.50)
        p75 = self.percentile(bucketed, 0.75)
        p25 = self.percentile(bucketed, 0.25)
        p90 = self.percentile(bucketed, 0.90)
        mode_counts = Counter(bucketed)
        recent_robust_median = self.find_robust_median(sample)
        ordered_sample = sorted(int(price) for price in sample)
        trim = int(len(ordered_sample) * 0.15)
        trimmed_sample = (
            ordered_sample[trim : len(ordered_sample) - trim]
            if len(ordered_sample) - 2 * trim >= 1
            else ordered_sample
        )
        recent_trimmed_mean = mean(trimmed_sample)
        recent_std = math.sqrt(
            sum((price - recent_trimmed_mean) ** 2 for price in trimmed_sample)
            / max(1, len(trimmed_sample))
        )
        mode_price, mode_count = max(
            mode_counts.items(),
            key=lambda item: (
                item[1],
                -abs(item[0] - int(round(recent_robust_median))),
            ),
        )
        mode_strength = mode_count / max(1, len(bucketed))

        stats_median = (
            artist_stats["median"]
            if artist_stats["count"] >= 3
            else global_stats["median"]
        )
        stats_mean = (
            artist_stats["mean"] if artist_stats["count"] >= 3 else global_stats["mean"]
        )
        stats_std = (
            artist_stats["std_dev"]
            if artist_stats["count"] >= 3
            else max(global_stats["std_dev"], 0.0)
        )
        median_price = 0.65 * recent_robust_median + 0.35 * stats_median
        mean_price = 0.65 * recent_trimmed_mean + 0.35 * stats_mean
        std_dev = 0.65 * recent_std + 0.35 * stats_std
        lower_anchor = self.find_lower_price_anchor_bid(current_painting)
        stable_mode = (
            len(sample) >= 5
            and mode_strength >= 0.35
            and std_dev <= max(4.0, 0.28 * max(1.0, median_price) + 2.0)
        )
        reference_price = 0.0
        if stable_mode:
            reference_price = (
                0.52 * mode_price + 0.28 * median_price + 0.20 * mean_price
            )
        else:
            reference_price = (
                0.45 * lower_anchor + 0.35 * median_price + 0.20 * mean_price
            )

        reference_price = max(lower_anchor, int(round(reference_price)))
        return {
            "mode_price": max(1, int(mode_price)),
            "mode_strength": mode_strength,
            "median_price": max(1, int(round(median_price))),
            "mean_price": max(1, int(round(mean_price))),
            "std_dev": max(0.0, float(std_dev)),
            "lower_anchor": lower_anchor,
            "reference_price": reference_price,
            "stable_mode": stable_mode,
            "percentile_50": p50,
            "percentile_75": p75,
            "percentile_25": p25,
            "percentile_90": p90,
        }

    def find_lower_price_anchor_bid(self, current_painting):
        artist_recent = list(self.recent_prices_by_artist[current_painting])[-10:]
        global_recent = list(self.recent_global_prices)[-15:]
        source = artist_recent if len(artist_recent) >= 3 else global_recent

        if not source:
            return max(1, int(round(self.ideal_budget_per_round)))

        ordered = sorted(int(price) for price in source)
        cutoff = max(1, int(math.ceil(len(ordered) * 0.45)))
        return max(1, int(round(sum(ordered[:cutoff]) / cutoff)))

    def decide_bid(self, state, features):
        progress = state["progress"]
        pace = state["pace"]
        my_paintings = state["my_paintings"]
        current_painting = state["current_painting"]

        marginal_gain = features["marginal_gain"]
        market_price = features["market_price"]
        scarcity_score = features["scarcity_score"]
        balance_pressure = features["balance_pressure"]
        artist_stats = features["artist_stats"]
        global_stats = features["global_stats"]
        volatile_exists = features["volatile_exists"]
        total_pressure = features["opponent_model"]["total_pressure"]
        average_threat = features["opponent_model"]["average_threat"]
        strongest_threat = features["opponent_model"]["strongest_threat"]
        learned_adjustment = features["learned_adjustment"]
        endgame_state = features["endgame_state"]
        endgame_urgency = endgame_state["urgency"]
        endgame_mode = endgame_state["mode"]
        current_count = my_paintings[current_painting]
        min_count = min(my_paintings.values())

        # price profile estimation to get a sense of the current market price for paintings of this artist based on recent auction history, which can help us understand the price we might have to pay to acquire this painting and inform our bid decision accordingly
        price_profile = self.find_price_stats(
            current_painting=current_painting,
            artist_stats=artist_stats,
            global_stats=global_stats,
        )

        # mode_price is the most common price observed in the recent auction history for this artist, which can give us a sense of the typical price we might expect to pay for this painting; mode_strength is how dominant that mode price is compared to other prices, which can help us understand how reliable that mode price might be as an indicator of the current market price; median_price and mean_price give us additional measures of central tendency in the recent prices, which can help us understand the overall distribution of prices and inform our bid decision; lower_anchor is a conservative estimate of the lower end of the price range based on recent history, which can help us avoid overbidding; reference_price is a blended estimate of the current market price based on the mode, median, and mean, which can serve as a key reference point for our bid decision; stable_mode indicates whether we have a strong and consistent mode price in the recent history, which can give us more confidence in using that mode price as a reference for our bidding strategy
        mode_price = price_profile["mode_price"]
        mode_strength = price_profile["mode_strength"]
        reference_price = price_profile["reference_price"]
        p50 = price_profile["percentile_50"]
        p75 = price_profile["percentile_75"]
        p25 = price_profile["percentile_25"]
        p90 = price_profile["percentile_90"]
        profile_std = price_profile["std_dev"]

        # if needed or not
        needed = (
            current_count == min_count
            or (current_count == 0 and progress >= 0.60)
            or endgame_mode == "must_convert"
        )

        # if each painting is seen atleast 3 times
        painting_order = state["painting_order"]
        current_round = state["current_round"]
        seen = painting_order[:current_round]
        counter = Counter(seen)

        # if each painting is seen 3 times, and have enough data then only bid, else give minimal bid
        if all(
            counter[artist] < 3
            for artist in ["Da Vinci", "Picasso", "Rembrandt", "Van Gogh"]
        ):
            return min(
                self.find_lower_price_anchor_bid(current_painting),
                10 + self.ideal_budget_per_round,
            ), needed

        # if we have better std
        if profile_std > 5:
            return min(
                self.find_lower_price_anchor_bid(current_painting),
                10 + self.ideal_budget_per_round,
            ), needed

        # if strongly needed
        strongly_needed = progress >= 0.60 and current_count == 0
        if strongly_needed:
            volatile_exists = True

        # desire to buy the painting from the reference
        desire_lift = math.log(0.5 + pace + progress) * (
            1.5 * marginal_gain
            + 2.5 * (scarcity_score)
            - 1.5 * balance_pressure
            + 0.3 * strongest_threat
            + 0.3 * average_threat
            + 1.5 * total_pressure
            + 2.5 * endgame_urgency
            + learned_adjustment
            + 0.5 * mode_strength
            + 0.5 * p25 / max(1, reference_price)
            + 0.5 * p50 / max(1, reference_price)
            + 0.5 * p75 / max(1, reference_price)
            + 0.9 * self.type_bid_adjustment.get(current_painting, 0.0)
            # punishing more if stringly needed
            + 0.3 * (reference_price if strongly_needed else 0)
        )

        lift = desire_lift / 8.0

        # adding hard cap for the limit
        hard_cap = (
            min(18, mode_price + (self.ideal_budget_per_round * 0.3))
            if volatile_exists
            else mode_price + 3
        )
        candidate_bid = min(market_price, hard_cap) + lift

        candidates = [candidate_bid]
        # only if volatile
        if volatile_exists:
            candidates.append(p90)
        candidate_bid = max(candidates)
        candidate_bid = min(candidate_bid, hard_cap)
        # if strongly needed
        if strongly_needed:
            candidate_bid = candidate_bid + 1
        return candidate_bid, needed
