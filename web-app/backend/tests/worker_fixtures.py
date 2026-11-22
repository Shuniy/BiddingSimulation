import random
import time


class Bot:
    name = "Worker test bot"

    def __init__(self):
        self.initial_bid = random.randint(1, 100)

    def get_bid(self, current_round, starting_budget, **_):
        if starting_budget == 500:
            time.sleep(30)
        if starting_budget == 600 and current_round == 0:
            raise RuntimeError("test crash")
        if starting_budget == 700:
            # Exiting the process is different from a normal Python exception.
            raise SystemExit(1)
        return self.initial_bid + random.randint(0, 10)
