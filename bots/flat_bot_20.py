class Bot(object):
    """
    Bids 20 on everything
    """

    def __init__(self, value=20):
        self.value = value
        self.name = f"Fixed Bid {self.value}"

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
        return self.value
