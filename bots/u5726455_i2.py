import math


class Bot(object):
    def __init__(self):
        self.name = "Adaptive Market Bidder"
        self.artists = ["Da Vinci", "Picasso", "Rembrandt", "Van Gogh"]

        # Regret / adaptation memory
        self.type_bid_adjustment = {artist: 0.0 for artist in self.artists}
        self.last_processed_history_len = 0

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
        # build a comprehensive state representation
        state = self.build_state(
            current_round=current_round,
            bots=bots,
            round_limit=round_limit,
            starting_budget=starting_budget,
            painting_order=painting_order,
            current_painting=current_painting,
            winner_ids=winner_ids,
            amounts_paid=amounts_paid,
        )

        # if we are out of budget, we can't bid
        if state["my_budget"] <= 0:
            return 0

        # update regret learning based on past outcomes
        self.update_learning(state)
        # extract features to inform our bid decision
        features = self.extract_features(state)
        # decide on a bid amount based on the state and features
        bid = self.decide_bid(state, features)

        return int(max(0, min(state["my_budget"], bid)))

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
    ):
        normalized_bots = [self.normalize_bot(bot) for bot in bots]
        my_bot = self.find_my_bot(normalized_bots)

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

    def find_my_bot(self, bots):
        for bot in bots:
            if str(bot["bot_name"]) == str(self.name):
                return bot
        return bots[0]

    # =========================
    # Learning / regret updates
    # =========================
    def update_learning(self, state):
        # update regrets and bid adjustments based on the history of wins/losses and prices paid
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

        # process new auction outcomes and update bid adjustments
        # usually will be the most recent auction, but if we missed updates for some reason it will catch up on all unprocessed history
        for i in range(self.last_processed_history_len, history_len):
            artist = painting_order[i]
            winner_id = winner_ids[i]
            paid = int(amounts_paid[i])

            if artist not in self.artists:
                continue

            # if we lost this auction, we want to increase our bid adjustment for this artist to try to win it next time;
            if winner_id != my_id:
                self.learn_from_loss(artist, paid)
            # if we won this auction, we want to decrease our bid adjustment for this artist to try to avoid overpaying next time
            else:
                self.learn_from_win(artist, paid)

            self.type_bid_adjustment[artist] = max(
                -3.0, min(4.0, self.type_bid_adjustment[artist])
            )

        # update the last processed history length to the current history length, so we only process new auctions next time
        self.last_processed_history_len = history_len

    def learn_from_loss(self, artist, paid):
        # learn from losing an auction for a painting of this artist - if we lost for a low price,
        # we likely underbid and should increase our bid adjustment more;
        # if we lost for a high price, we were close but still lost,
        # so we should increase our bid adjustment but not as much;
        # if we lost for a very high price, we might have been too aggressive and
        # should be careful about increasing our bid adjustment too much
        if paid <= 10:
            self.type_bid_adjustment[artist] += 0.20
        elif paid <= 15:
            self.type_bid_adjustment[artist] += 0.10
        elif paid <= 25:
            self.type_bid_adjustment[artist] += 0.03
        else:
            self.type_bid_adjustment[artist] -= 0.02

    def learn_from_win(self, artist, paid):
        # learn from winning an auction for a painting of this artist -
        # if we won but paid a high price,
        # we likely overbid and should decrease our bid adjustment to try to avoid overpaying next time;
        # if we won and paid a moderate price, we might be in a good range
        # but could still try to be a bit more efficient by decreasing our bid adjustment slightly;
        # if we won and paid a low price,
        # we might have been able to bid even less and still win,
        # so we should decrease our bid adjustment a bit more to try to find that more efficient winning bid next
        if paid >= 25:
            self.type_bid_adjustment[artist] -= 0.15
        elif paid >= 18:
            self.type_bid_adjustment[artist] -= 0.08
        elif paid <= 10:
            self.type_bid_adjustment[artist] += 0.03

    # =========================
    # Feature extraction
    # =========================
    def extract_features(self, state):
        # extract various features from the current state to inform our bid decision, such as:
        # - how many paintings of the current artist are still available in the future (supply/ scarcity)
        # - how many paintings of the current artist we already have and how much would it increase our score (value/ marginal gain)
        # - what is the current market price for paintings of this artist based on recent auction history (market price estimation)
        # - how strong are our opponents' needs and budgets for this painting based on their past behaviour (opponent modelling)
        current_painting = state["current_painting"]
        my_paintings = state["my_paintings"]
        painting_order = state["painting_order"]
        current_round = state["current_round"]
        amounts_paid = state["amounts_paid"]

        # get supply/scarcity features
        remaining_supply = self.get_remaining_supply(painting_order, current_round)
        # get supply in near future windows to capture local urgency beyond overall scarcity
        future_window_supply = self.get_future_window_supply(
            painting_order, current_round, window_sizes=[8, 20, 50]
        )

        # current score
        current_score = self.product_score(my_paintings)
        # marginal gain if we acquire this painting - how much would our score increase if we win this painting,
        # which captures the value of this painting to us based on our current collection
        marginal_gain = self.marginal_product_gain(my_paintings, current_painting)

        # market price estimation based on recent auction history for this artist and overall, which can help us understand the price we might have to pay to acquire this painting
        market_price = self.estimate_market_price(
            current_painting=current_painting,
            painting_order=painting_order,
            amounts_paid=amounts_paid,
        )

        # opponent modelling to assess the threat level of our opponents
        # for this painting based on their past wins, prices paid,
        # and focus on this artist, which can help us understand
        # how competitive the auction for this painting might be and how much pressure
        # we might face from opponents who really want it
        opponent_model = self.model_opponents(state, market_price)

        # scarcity score that combines overall remaining supply and local urgency based on future window supply to capture both how scarce this painting is overall and how urgently we might need to acquire it based on the near future supply, which can help inform how much we should value this painting in our bid decision
        scarcity_score = self.compute_scarcity_score(
            current_painting=current_painting,
            remaining_supply=remaining_supply,
            future_window_supply=future_window_supply,
        )

        # pressure to balance our collection based on
        # how many paintings of this artist we already have compared to our least collected artist,
        # which can help us understand how much we might want to acquire this painting to maintain a balanced collection
        # and avoid having a weak category that could limit our score
        balance_pressure = self.compute_balance_pressure(
            my_paintings=my_paintings, current_painting=current_painting
        )

        # learnt regret adjustment for this artist based on our past wins/losses and prices paid, which can help us adapt our bidding strategy for this artist over time based on our experience in the auctions so far
        learned_adjustment = self.type_bid_adjustment.get(current_painting, 0.0)

        # compute endgame state based on our progress in the game, our budget, our collection, and the remaining supply of this artist, which can help us understand how urgently we might need to acquire this painting and how much risk we might want to take in our bid decision as we approach the endgame where we need to convert our budget into score efficiently to maximize our chances of winning
        endgame_state = self.compute_endgame_state(
            state=state, remaining_supply=remaining_supply
        )

        return {
            "remaining_supply": remaining_supply,
            "future_window_supply": future_window_supply,
            "current_score": current_score,
            "marginal_gain": marginal_gain,
            "market_price": market_price,
            "opponent_model": opponent_model,
            "scarcity_score": scarcity_score,
            "balance_pressure": balance_pressure,
            "learned_adjustment": learned_adjustment,
            "endgame_state": endgame_state,
        }

    # =========================
    # Supply / scarcity
    # =========================
    def get_remaining_supply(self, painting_order, current_round):
        # get a count of how many paintings of each artist are still available in the future rounds, which can inform our sense of scarcity and how urgently we need to acquire paintings of this artist
        counts = {artist: 0 for artist in self.artists}
        future_paintings = painting_order[current_round:]
        for artist in future_paintings:
            if artist in counts:
                counts[artist] += 1
        return counts

    def get_future_window_supply(self, painting_order, current_round, window_sizes):
        # get supply counts for different future windows to capture not just overall scarcity but also local urgency -
        # for example, if there are many paintings of this artist later on but none in the next 10 rounds,
        # that creates a sense of urgency to acquire this painting now even if overall scarcity is not too high
        result = {}
        for window in window_sizes:
            counts = {artist: 0 for artist in self.artists}
            future_slice = painting_order[current_round : current_round + window]
            for artist in future_slice:
                if artist in counts:
                    counts[artist] += 1
            result[window] = counts
        return result

    def compute_scarcity_score(
        self, current_painting, remaining_supply, future_window_supply
    ):
        # combine overall remaining supply and local urgency based on future window supply to compute a scarcity score for this painting, which can help us understand how scarce this painting is and how urgently we might need to acquire it based on the near future supply -
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

    # =========================
    # Value / score
    # =========================
    def product_score(self, paintings):
        # get our current score based on the paintings we have - in this game, the score is the product of the counts of each artist,
        score = 1
        for artist in self.artists:
            score *= max(0, int(paintings.get(artist, 0)))
        return score

    def marginal_product_gain(self, my_paintings, current_painting):
        # get marginal gain in our score if we acquire this painting, which can help us understand the value of this painting to us based on our current collection -
        old_score = self.product_score(my_paintings)
        new_paintings = dict(my_paintings)
        new_paintings[current_painting] += 1
        new_score = self.product_score(new_paintings)
        return new_score - old_score

    def compute_balance_pressure(self, my_paintings, current_painting):
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

    # =========================
    # Market price estimation
    # =========================
    def estimate_market_price(self, current_painting, painting_order, amounts_paid):
        # if we have no history, we can start with a base estimate of 1
        if not amounts_paid:
            return 1

        # history_types represents the artists of the paintings
        # that have been auctioned so far, aligned with the amounts_paid history
        history_types = painting_order[: len(amounts_paid)]

        # here we filter the amounts_paid history to only include prices for paintings of the current artist,
        # which can give us a more relevant sample for estimating the market price for this artist
        # fetching the most recent prices for this artist to capture current market conditions, while also considering overall price history for robustness
        type_prices = [
            price
            for price, artist in zip(amounts_paid, history_types)
            if artist == current_painting
        ]

        # get the most recent prices overall to have a broader sample of market conditions, which can help smooth out anomalies in the artist-specific history and
        # provide a more stable estimate
        recent_all = amounts_paid[-10:] if len(amounts_paid) >= 10 else amounts_paid

        # if we have no price history for this artist,
        # we can fall back to a blended estimate based on the overall recent price history,
        # which allows us to still have an informed estimate even without artist-specific data
        if not type_prices:
            return max(1, int(self.robust_median(recent_all)))

        # if we do have price history for this artist,
        # we can use a blend of the median price for this artist and
        # the median price overall to get a more informed estimate
        # the artist-specific median captures the typical price for this artist,
        # while the overall median helps smooth out any anomalies and provides
        # context on the general market conditions
        recent_type_prices = type_prices[-6:] if len(type_prices) >= 6 else type_prices

        # type_estimate is based on the recent prices for this specific artist, which gives us a focused estimate of the market price for this artist based on the most relevant historical data
        type_estimate = self.robust_median(recent_type_prices)
        # all_estimate is based on the recent prices for all artists, which provides a broader context of the market conditions and can help smooth out any anomalies in the artist-specific history, giving us a more stable estimate to blend with the artist-specific estimate
        all_estimate = self.robust_median(recent_all)

        # blend the artist-specific estimate and the overall estimate to get a final market price estimate, which allows us to leverage the most relevant data for this artist while also incorporating broader market trends for a more informed and robust estimate
        blended = 0.7 * type_estimate + 0.3 * all_estimate
        return max(1, int(blended))

    def robust_median(self, values):
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

    # =========================
    # Opponent modelling
    # =========================
    def build_opponent_history(self, state):
        # build a history of our opponents' wins, prices paid,
        # and focus on each artist based on the auction history so far,
        # which can help us model their behaviour and assess how much they might want the current painting
        # based on their past actions -
        # for example, if an opponent has won many paintings of the current artist and
        # paid high prices for them, they might have a strong desire to acquire more paintings of
        # this artist and could be a strong competitor in the auction for the current painting
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
        # compute how much an opponent might need the current painting based on how many paintings of this artist they already have compared to us -
        opp_count = opponent_paintings[current_painting]
        base_need = 1.0 / (opp_count + 1)
        if opp_count < my_current_count:
            base_need += 0.15
        return min(1.0, base_need)

    def compute_budget_strength(self, opponent_budget, starting_budget):
        # compute how strong an opponent's budget is relative to the starting budget, which can help us understand how much financial capacity they have left to compete for this painting and how aggressive they might be able to be in their bidding -
        return min(1.0, opponent_budget / max(1, starting_budget))

    def compute_score_pressure(self, opponent_score, my_score):
        # compute score pressure based on the opponent's current score compared to ours, which can help us understand how motivated they might be to acquire this painting to catch up or maintain their lead in terms of score -
        if opponent_score < my_score:
            gap_ratio = (my_score - opponent_score) / max(1, my_score)
            return min(1.0, 0.4 + gap_ratio)
        return 0.4

    def compute_artist_aggression(
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

    def compute_price_aggression(self, opp_history, current_painting, market_price):
        # compute price aggression based on the opponent's past prices paid for this artist compared to the current market price, which can help us understand how aggressive they might be in their bidding for this painting based on their demonstrated willingness to pay for paintings of this artist in the past -
        if not opp_history:
            return 0.0

        prices = opp_history["prices_by_artist"][current_painting]
        if not prices or market_price <= 0:
            return 0.0

        avg_price = sum(prices) / len(prices)
        ratio = avg_price / market_price
        return min(1.0, ratio / 2.0)

    def combine_opponent_threat_advanced(
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
        # get history of opponents' behaviour to inform our modelling of their threat level for this painting based on their past wins, prices paid, and focus on this artist
        opponent_history = self.build_opponent_history(state)

        opponent_profiles = []
        threat_values = []

        # for each opponent, compute various features of their behaviour and situation to assess how much of a threat they might be in the auction for the current painting -
        for opp in opponents:
            opp_id = opp["bot_unique_id"]
            opp_hist = opponent_history.get(opp_id)

            # compute opponent's need for this painting based on how many paintings of this artist they already have compared to us, which gives us a sense of how much they might want this painting and how competitive the auction might be
            opp_need = self.compute_opponent_need(
                opponent_paintings=opp["paintings"],
                current_painting=current_painting,
                my_current_count=my_current_count,
            )

            # compute opponent's budget strength relative to the starting budget, which helps us understand how much financial capacity they have left to compete for this painting and how aggressive they might be able to be in their bidding
            budget_strength = self.compute_budget_strength(
                opponent_budget=opp["budget"], starting_budget=starting_budget
            )

            # compute score pressure based on the opponent's current score compared to ours, which can help us understand how motivated they might be to acquire this painting to catch up or maintain their lead in terms of score
            score_pressure = self.compute_score_pressure(
                opponent_score=opp["score"], my_score=my_score
            )

            # compute artist aggression based on the opponent's past wins and focus on this artist, which can help us understand how aggressive they might be in bidding for this painting based on their demonstrated interest and success with this artist in the past
            artist_aggression = self.compute_artist_aggression(
                opp_history=opp_hist,
                current_painting=current_painting,
                total_rounds_played=total_rounds_played,
            )

            # compute price aggression based on the opponent's past prices paid for this artist compared to the current market price, which can help us understand how aggressive they might be in their bidding for this painting based on their demonstrated willingness to pay for paintings of this artist in the past
            price_aggression = self.compute_price_aggression(
                opp_history=opp_hist,
                current_painting=current_painting,
                market_price=market_price,
            )

            # threat is a combined measure of how much of a competitive threat this opponent might be in the auction for the current painting based on their need for it, their budget strength, the score pressure they are under, and their demonstrated aggression in terms of both their focus on this artist and their willingness to pay for it in the past
            threat = self.combine_opponent_threat_advanced(
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

    # =========================
    # Endgame analysis
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

    # =========================
    # Lightweight anti-predictability
    # =========================
    def deterministic_jitter(self, current_round, current_painting):
        """
        Tiny deterministic jitter in {-1, 0, 1}.
        Keeps behaviour less predictable without making the bot erratic.
        """
        seed = (current_round * 17 + len(current_painting) * 13) % 5
        if seed == 0:
            return -1
        elif seed == 1:
            return 1
        return 0

    def stochastic_bid_jitter(self, state, features, candidate_bid):
        """
        Very small randomisation around the candidate bid.
        Slightly increases when we are near the market threshold or in urgent endgame.
        """
        current_round = state["current_round"]
        current_painting = state["current_painting"]
        market_price = features["market_price"]
        scarcity_score = features["scarcity_score"]
        total_pressure = features["opponent_model"]["total_pressure"]
        endgame_mode = features["endgame_state"]["mode"]

        jitter = self.deterministic_jitter(current_round, current_painting)

        near_threshold = abs(candidate_bid - market_price) <= 2

        if near_threshold and total_pressure >= 0.35:
            jitter += 1

        if scarcity_score >= 0.5 and endgame_mode != "normal":
            jitter += 1

        return max(-1, min(2, jitter))

    # =========================
    # Bid decision
    # =========================
    def decide_bid(self, state, features):
        my_budget = state["my_budget"]
        starting_budget = state["starting_budget"]
        progress = state["progress"]
        remaining_rounds = state["remaining_rounds"]

        marginal_gain = features["marginal_gain"]
        market_price = features["market_price"]
        scarcity_score = features["scarcity_score"]
        balance_pressure = features["balance_pressure"]
        total_pressure = features["opponent_model"]["total_pressure"]
        learned_adjustment = features["learned_adjustment"]
        endgame_state = features["endgame_state"]
        endgame_urgency = endgame_state["urgency"]
        endgame_mode = endgame_state["mode"]

        normalized_gain = math.sqrt(max(0, marginal_gain))

        desire_score = (
            0.50 * normalized_gain
            + 10.0 * scarcity_score
            + 7.0 * balance_pressure
            + 5.0 * total_pressure
            + 8.0 * endgame_urgency
        )

        lift = desire_score / 8.0
        candidate_bid = market_price + lift + learned_adjustment

        if progress < 0.25:
            candidate_bid *= 0.92
        elif progress > 0.80:
            candidate_bid *= 1.12

        if endgame_mode == "late_game":
            candidate_bid *= 1.08
        elif endgame_mode == "must_convert":
            candidate_bid *= 1.22

        budget_ratio = my_budget / max(1, starting_budget)
        budget_per_remaining_round = my_budget / max(1, remaining_rounds)

        if budget_ratio < 0.20:
            candidate_bid *= 0.75
        elif budget_ratio > 0.65 and progress > 0.60:
            candidate_bid *= 1.08

        if scarcity_score < 0.20 and balance_pressure < 0.30:
            candidate_bid *= 0.80

        if marginal_gain > 0 and balance_pressure >= 0.60:
            candidate_bid = max(candidate_bid, market_price + 1)

        if progress < 0.33:
            phase_cap = max(12, int(my_budget * 0.08))
        elif progress < 0.75:
            phase_cap = max(14, int(my_budget * 0.14))
        else:
            phase_cap = max(20, int(my_budget * 0.30))

        pacing_cap = max(10, int(budget_per_remaining_round * 1.8))
        hard_cap = min(my_budget, max(phase_cap, pacing_cap))

        if endgame_mode == "late_game" and endgame_urgency >= 0.5:
            hard_cap = min(
                my_budget, max(hard_cap, int(budget_per_remaining_round * 2.5))
            )

        if endgame_mode == "must_convert":
            hard_cap = min(
                my_budget, max(hard_cap, int(budget_per_remaining_round * 4.0))
            )

        candidate_bid = min(candidate_bid, hard_cap)

        if endgame_mode == "must_convert" and endgame_urgency >= 0.6:
            candidate_bid = max(candidate_bid, market_price + 2)

        jitter = self.stochastic_bid_jitter(state, features, candidate_bid)
        candidate_bid += jitter

        candidate_bid = min(candidate_bid, my_budget)
        candidate_bid = max(0, candidate_bid)

        if marginal_gain == 0 and scarcity_score < 0.15 and balance_pressure <= 0.10:
            return min(my_budget, max(0, market_price - 1))

        return int(math.floor(candidate_bid))
