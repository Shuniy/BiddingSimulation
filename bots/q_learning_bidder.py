"""
Frozen tabular Q-policy bot with a heuristic fallback for tiny rooms.

Methodology:
1. Encode the current state using phase, need level, scarcity, budget pace, and
   opponent pressure.
2. Look up the best action in the offline-trained Q-table.
3. If the state is missing from the table, fall back to a simple heuristic
   action choice.
4. Decode the chosen action into a bid amount.
5. In very small rooms, use the original heuristic bid instead of the Q-table.

Design choices:
- The large Q-table is the learned policy and is left unchanged.
- The heuristic fallback is there because the learned table is less reliable in
  very small rooms.
- Only explanatory comments/docs were added here.
"""

import math
from statistics import mean


class Bot(object):
    """
    Frozen tabular Q-policy trained offline, with a small heuristic fallback
    for tiny rooms where the learned table was too brittle.
    """

    ARTISTS = ("Da Vinci", "Picasso", "Rembrandt", "Van Gogh")
    Q_TABLE = {
        (0, 0, 2, 0, 0): [21.5279, 21.4388, 21.5073, 22.9781, 22.3841, 23.2358, 23.9032, 25.8632],
        (0, 0, 2, 0, 1): [18.6207, 20.1043, 21.9342, 21.1427, 21.6718, 21.5939, 21.3528, 22.787],
        (0, 0, 2, 0, 2): [17.7091, 17.5027, 17.8207, 17.2317, 17.5201, 17.123, 17.0497, 19.6084],
        (0, 2, 2, 0, 0): [22.7429, 24.5018, 24.2485, 25.1797, 25.8367, 28.3325, 28.0988, 29.1447],
        (0, 2, 2, 0, 1): [8.9643, 15.2295, 19.7333, 23.4693, 17.5508, 23.8844, 19.1886, 28.0749],
        (0, 2, 2, 0, 2): [21.4317, 20.8425, 21.8268, 22.0552, 22.0557, 22.0943, 22.0913, 22.3179],
        (0, 3, 0, 0, 2): [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (0, 3, 0, 1, 2): [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (0, 3, 2, 0, 0): [22.3558, 23.325, 22.7752, 23.7123, 25.0584, 27.1142, 25.6367, 25.8487],
        (0, 3, 2, 0, 1): [24.0987, 24.4021, 24.1898, 24.6248, 24.4356, 24.8929, 25.6907, 24.8003],
        (0, 3, 2, 0, 2): [19.5386, 19.8138, 20.5985, 19.9456, 20.1863, 21.2141, 20.5292, 21.7835],
        (1, 1, 2, 0, 0): [6.2715, 6.4714, 6.5975, 6.8198, 6.6012, 6.812, 6.8403, 7.0958],
        (1, 1, 2, 0, 1): [4.6879, 4.5881, 4.5629, 5.5252, 5.0682, 4.8832, 4.5471, 4.5968],
        (1, 1, 2, 0, 2): [6.0588, 6.0394, 5.9965, 6.101, 6.1059, 6.8306, 6.0804, 6.1246],
        (1, 1, 2, 1, 2): [0.0, 0.0, 0.0, 0.0, 1.1698, 0.0, 0.2841, 0.0],
        (1, 2, 2, 0, 0): [6.3556, 6.3049, 6.2853, 6.3279, 6.4377, 6.8456, 6.3817, 6.3843],
        (1, 2, 2, 0, 1): [4.7372, 4.707, 4.7335, 4.7667, 4.7556, 4.7311, 4.8778, 5.5444],
        (1, 2, 2, 0, 2): [6.2969, 6.1177, 6.3421, 6.3504, 6.5691, 7.7748, 6.3533, 6.3961],
        (1, 2, 2, 1, 2): [0.0637, 0.0236, 0.0, 0.0, 0.0089, 0.7965, 0.0, 0.0],
        (1, 3, 2, 0, 0): [5.9338, 5.6961, 5.8856, 5.9052, 5.8994, 6.1404, 6.1477, 6.1354],
        (1, 3, 2, 0, 1): [4.5254, 4.4732, 5.3039, 4.6151, 4.6071, 4.5807, 4.5387, 4.3077],
        (1, 3, 2, 0, 2): [6.0154, 6.0921, 5.9332, 6.0188, 6.3398, 6.1444, 6.0503, 6.0662],
        (1, 3, 2, 1, 0): [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (1, 3, 2, 1, 2): [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.0682, 0.0],
        (2, 1, 0, 0, 0): [22.2836, 48.2745, 24.8742, 24.4506, 24.6568, 25.1323, 26.3413, 22.3745],
        (2, 1, 0, 0, 1): [16.6499, 18.6644, 13.1802, 55.5082, 8.2164, 11.022, 15.3734, 13.1509],
        (2, 1, 0, 0, 2): [35.2076, 27.3817, 46.063, 30.093, 32.3471, 28.2157, 27.6685, 19.85],
        (2, 1, 0, 1, 0): [31.2233, 0.0, 0.0, 4.0071, 0.0, 0.9693, 0.0, 3.416],
        (2, 1, 0, 1, 1): [46.5538, 0.0, 0.0, 0.0, 0.0, 4.5766, 0.0, 0.0],
        (2, 1, 0, 1, 2): [39.6312, 2.0274, 1.284, 0.0, 6.4792, 0.0, 3.3073, 1.6913],
        (2, 1, 0, 2, 0): [25.4009, 0.0, 0.0, 0.0, 1.3432, 0.0, 0.0, 0.0],
        (2, 1, 0, 2, 2): [37.7692, 0.0, 0.0, 2.4123, 1.2909, 0.0, 2.4928, 0.0],
        (2, 1, 1, 0, 0): [6.5755, 0.4963, 0.0, 0.0, 0.0, 0.0, 1.7604, 0.0],
        (2, 1, 1, 0, 1): [1.3978, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 1, 1, 0, 2): [0.0, 0.4616, 1.7298, 0.2055, 0.0, 0.9495, 4.8249, 0.0],
        (2, 1, 2, 0, 0): [9.0102, 8.9087, 8.9872, 9.9593, 8.833, 8.6767, 9.7922, 8.7287],
        (2, 1, 2, 0, 1): [8.7527, 8.609, 9.7114, 8.5083, 8.5923, 8.7644, 8.7538, 8.7532],
        (2, 1, 2, 0, 2): [8.7566, 8.6572, 10.1795, 8.6799, 8.7487, 8.6287, 8.7555, 8.6484],
        (2, 1, 2, 1, 0): [5.847, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.6823],
        (2, 1, 2, 1, 2): [3.0675, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 17.7804],
        (2, 1, 2, 2, 2): [0.2711, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 0, 0, 0): [41.1783, 14.2403, 7.4333, 12.4111, 13.5348, 18.8551, 8.1447, 2.178],
        (2, 2, 0, 0, 1): [48.6928, 0.0, 7.6306, 0.0, 5.2664, 1.5149, 3.5465, 3.0645],
        (2, 2, 0, 0, 2): [50.8049, 11.4961, 10.2758, 0.0, 2.0769, 11.7526, 5.7643, 14.0955],
        (2, 2, 0, 1, 0): [14.5495, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 0, 1, 1): [34.3913, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 0, 1, 2): [42.4531, 1.1732, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 0, 2, 0): [12.0445, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 0, 2, 2): [38.5624, 0.0, 0.0, 3.4209, 1.0447, 1.1881, 3.9486, 0.0],
        (2, 2, 1, 0, 0): [3.9248, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 1, 0, 2): [0.8331, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 2, 0, 0): [9.7701, 8.3758, 7.1854, 7.7801, 7.7192, 7.6694, 7.602, 7.3502],
        (2, 2, 2, 0, 1): [9.0455, 7.4773, 10.6912, 9.0737, 7.01, 7.916, 7.3422, 8.5152],
        (2, 2, 2, 0, 2): [10.7179, 8.9328, 8.9394, 8.8748, 8.9702, 8.9023, 8.8839, 8.8925],
        (2, 2, 2, 1, 0): [4.5577, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 2, 1, 2): [18.2256, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 2, 2, 0): [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 2, 2, 2, 2): [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 3, 0, 0, 0): [26.835, 24.7655, 45.303, 26.5483, 21.3699, 25.3044, 28.6735, 28.4455],
        (2, 3, 0, 0, 1): [23.6665, 21.3967, 20.0566, 55.3129, 18.7115, 26.7951, 19.3243, 16.27],
        (2, 3, 0, 0, 2): [54.3289, 25.4787, 38.0723, 38.3995, 31.3505, 27.9423, 29.16, 29.5946],
        (2, 3, 0, 1, 0): [39.6139, 7.6356, 0.0, 1.1753, 1.3372, 0.0, 0.0, 0.0],
        (2, 3, 0, 1, 1): [54.0239, 0.0, 3.3766, 0.0, 0.0, 0.0, 0.0, 3.6737],
        (2, 3, 0, 1, 2): [39.621, 3.2952, 0.0, 1.3925, 0.0, 0.9018, 2.7045, 0.0],
        (2, 3, 0, 2, 0): [28.7275, 0.0, 0.0, 0.0, 3.5751, 0.0, 0.0, 0.0],
        (2, 3, 0, 2, 2): [33.8073, 5.5996, 0.0, 0.0, 0.0, 3.1812, 2.0278, 0.0],
        (2, 3, 1, 0, 0): [0.376, 0.0, 0.0, 0.0, 7.0152, 0.0, 1.2056, 1.3632],
        (2, 3, 1, 0, 1): [0.0, 3.3182, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        (2, 3, 1, 0, 2): [4.5993, 0.3657, 0.0, 0.0, 0.4721, 0.0, 0.0, 0.0],
        (2, 3, 2, 0, 0): [8.9823, 9.1118, 9.0832, 9.1041, 9.1226, 10.8789, 9.0038, 9.1262],
        (2, 3, 2, 0, 1): [11.5149, 8.8979, 8.9189, 8.8937, 8.989, 8.9853, 8.8852, 8.8137],
        (2, 3, 2, 0, 2): [8.737, 11.709, 8.8058, 8.7208, 8.7363, 8.7506, 8.7558, 8.7839],
        (2, 3, 2, 1, 0): [10.4341, 1.7561, 1.8378, 0.0, 0.2803, 0.0, 0.0, 0.5624],
        (2, 3, 2, 1, 2): [21.1249, 0.8666, 0.0, 1.7873, 0.0, 0.0, 0.0, 2.4345],
    }

    def __init__(self):
        self.name = "Q-Learning Bidder"

    def _opponent_summary(
        self,
        bots,
        my_unique_id,
        current_painting,
        current_round,
        starting_budget,
        remaining_rounds,
    ):
        """Estimate local pressure for the current artist."""

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

            if not needs_current:
                continue

            urgent_prices.append(avg_price)
            market_pressure.append(bot["budget"] / max(1, remaining_rounds))

            if wins >= 5 and 8 <= avg_price <= 12:
                flat_floor = 10

        if not urgent_prices or max(urgent_prices) < 8:
            pressure_bin = 0
        elif max(urgent_prices) < 13:
            pressure_bin = 1
        else:
            pressure_bin = 2

        market = mean(market_pressure) if market_pressure else 0.0
        return pressure_bin, market, flat_floor, volatile_exists

    def _encode_state(
        self,
        current_round,
        round_limit,
        starting_budget,
        painting_order,
        bots,
        my_bot_details,
        current_painting,
    ):
        """Encode the current auction state into a compact tabular key."""

        counts = my_bot_details["paintings"]
        min_count = min(counts.values())
        current_count = counts[current_painting]
        remaining_rounds = max(1, round_limit - current_round)
        remaining_current = max(1, painting_order[current_round:].count(current_painting))
        scarcity = remaining_rounds / remaining_current
        pace = my_bot_details["budget"] / remaining_rounds

        phase_bin = 0 if min_count == 0 else (1 if current_round < 150 else 2)
        if current_count == 0:
            need_bin = 0
        elif current_count == min_count:
            need_bin = 1
        elif current_count == min_count + 1:
            need_bin = 2
        else:
            need_bin = 3

        scarcity_bin = 0 if scarcity < 1.05 else (1 if scarcity < 1.25 else 2)
        budget_bin = 0 if pace < 6 else (1 if pace < 10 else 2)

        pressure_bin, market, flat_floor, volatile_exists = self._opponent_summary(
            bots=bots,
            my_unique_id=my_bot_details["bot_unique_id"],
            current_painting=current_painting,
            current_round=current_round,
            starting_budget=starting_budget,
            remaining_rounds=remaining_rounds,
        )

        state = (phase_bin, need_bin, scarcity_bin, budget_bin, pressure_bin)
        return state, scarcity, market, flat_floor, volatile_exists

    def _fallback_action(self, state):
        """Fallback action for states not present in the Q-table."""

        _, need_bin, _, _, pressure_bin = state
        if need_bin == 0:
            return 3 if pressure_bin < 2 else 5
        if need_bin == 1:
            return {0: 2, 1: 3, 2: 5}[pressure_bin]
        if need_bin == 2:
            return 1 if pressure_bin == 0 else 2
        return 0

    def _best_action(self, state):
        """Pick the highest-valued action from the learned Q-table."""

        values = self.Q_TABLE.get(state)
        if values is None:
            return self._fallback_action(state)

        best_value = max(values)
        for action, value in enumerate(values):
            if value == best_value:
                return action
        return 0

    def _decode_action(self, action, budget, current_round, round_limit):
        """Map a discrete action index to a concrete bid."""

        pace = max(1, int(budget / max(1, round_limit - current_round)))
        bid = {
            0: 0,
            1: pace,
            2: 10,
            3: 11,
            4: 15,
            5: 16,
            6: max(20, 2 * pace),
            7: max(30, 3 * pace),
        }[action]
        return int(max(0, min(budget, bid)))

    def _heuristic_bid(
        self,
        current_round,
        round_limit,
        my_budget,
        current_count,
        min_count,
        scarcity,
        market,
        flat_floor,
        volatile_exists,
    ):
        """Original heuristic fallback used in tiny rooms."""

        remaining_rounds = max(1, round_limit - current_round)
        lead = current_count - min_count
        marginal_gain = math.log(current_count + 2) - math.log(current_count + 1)

        raw_bid = (
            (my_budget / remaining_rounds)
            * (
                0.8
                + 7.5 * marginal_gain
                - 0.25 * max(0, lead)
                + 0.25 * max(0.0, scarcity - 1.0)
            )
            + 0.7 * market
        )

        if min_count == 0 and current_count == 0:
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

        return int(max(0, min(my_budget, raw_bid)))

    def _q_bid(
        self,
        state,
        current_round,
        round_limit,
        my_budget,
    ):
        """Use the learned action and apply the original safety overlay."""

        _, need_bin, scarcity_bin, budget_bin, pressure_bin = state
        action = self._best_action(state)

        if need_bin in (0, 1):
            floor_action = 2 if pressure_bin < 2 else 4
            beat_action = 3 if pressure_bin < 2 else 5
            action = max(action, floor_action)
            if need_bin == 0 or scarcity_bin == 2:
                action = max(action, beat_action)
            if scarcity_bin == 0 and pressure_bin == 0 and need_bin == 1:
                action = min(action, 3)
        elif need_bin == 2 and action == 0:
            action = 1
        else:
            action = min(action, 1)

        if action == 7 and budget_bin == 0:
            action = 6

        return self._decode_action(action, my_budget, current_round, round_limit)

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
        """Return the original Q-policy bid, with heuristic fallback in tiny rooms."""

        my_budget = my_bot_details["budget"]
        if my_budget <= 0:
            return 0

        counts = my_bot_details["paintings"]
        min_count = min(counts.values())
        current_count = counts[current_painting]

        state, scarcity, market, flat_floor, volatile_exists = self._encode_state(
            current_round=current_round,
            round_limit=round_limit,
            starting_budget=starting_budget,
            painting_order=painting_order,
            bots=bots,
            my_bot_details=my_bot_details,
            current_painting=current_painting,
        )

        if len(bots) <= 4:
            return self._heuristic_bid(
                current_round=current_round,
                round_limit=round_limit,
                my_budget=my_budget,
                current_count=current_count,
                min_count=min_count,
                scarcity=scarcity,
                market=market,
                flat_floor=flat_floor,
                volatile_exists=volatile_exists,
            )

        return self._q_bid(
            state=state,
            current_round=current_round,
            round_limit=round_limit,
            my_budget=my_budget,
        )
