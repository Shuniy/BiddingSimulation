# Bot World

## arena.py
Here you can run auctions with different bots and see the results. 

You can run an auction game like this:

	from auctioneer import Auctioneer
	my_auction = Auctioneer(<ADD ANY VARIABLES YOU WANT TO HERE>)
	winners = my_auction.run_auction()

`run_auction()` returns a list of winning bot names. For example, if the Random Budget Bidder wins, it returns `["Random Budget Bidder"]`.

The arena file has some example functions that show how to run auctions with different bots and different variables. 

## Bots

Use the module names to import bots in Python. The web arena and auction results show the strategy names.

| Strategy name | Python module | How it bids |
| --- | --- | --- |
| Collection Balancer | `bots.u5726455` | Prioritizes artists with the fewest paintings in its collection, adjusting for scarcity and remaining budget. |
| Room-Size Bidder | `bots.u5726455_i` | Uses different pricing and spending rules in small and large rooms. |
| Adaptive Market Bidder | `bots.u5726455_i2` | Estimates market prices from past sales and adjusts its bids based on recent wins and losses. |
| Fixed-Bid Specialist | `bots.u5726455_i2_i` | Detects recurring fixed prices and bids above them when it needs the artist. |
| Weighted Strategy Blend | `bots.u5726455_i2_i_i2_i` | Combines collection, supply, market, and room signals, blending in a second strategy for long and some short auctions. |
| Budget Reserve Bidder | `bots.u5726455_i_i2` | Reserves part of its starting budget while many rounds remain and relaxes spending caps as the auction progresses. |
| Endgame Boost Bidder | `bots.u5726455_i_i2_min` | Adds small bid increases for opponent pressure and paintings it still needs late in the auction. |
| Q-Learning Bidder | `bots.u5726455_q` | Uses an offline-trained Q-table in larger rooms and a heuristic in rooms of up to four bots. |
| Price Profile Bidder | `bots.u5726455_final` | Builds price profiles from auction history and anchors bids to lower observed prices when prices vary widely or history is sparse. |
| Random Budget Bidder | `bots.random_bot` | Picks a random bid from zero through its remaining budget. |
| Fixed Bid 10 | `bots.flat_bot_10` | Bids 10 every round. |
| Fixed Bid 15 | `bots.flat_bot_15` | Bids 15 every round by default. |
| Fixed Bid 20 | `bots.flat_bot_20` | Bids 20 every round by default. |

## auctioneer.py
DO NOT CHANGE THE CODE IN THE AUCTIONEER. THIS IS THE EXACT FILE WE WILL USE TO MARK YOUR BOT
IF YOU CHANGE SOMETHING IN THE AUCTIONEER FILE THEN YOUR BOT MIGHT NOT RUN PROPERLY WHEN WE MARK IT 

You DO NOT need to understand how the auctioneer works to complete this coursework and do well. 
But it always helps to understand software that you are using. 

The auctioneer runs the auctions.
Each auction consists of 200 rounds, with one painting auctioned each round.

### How to Use
There is some code at the bottom of auctioneer.py that runs an auction for you. You can run that by running auctioneer.py from terminal

	python3 auctioneer.py

### How It Works

#### Initialising the auction
The auctioneer is given the set of rules for the game and a "room", which is a list of the bots that will play. 
The auctioneer begins by initialising itself in the method self.__init__(), and initialising the bots with the method initialise_bots(). 

#### Running the auction
Once all the bots are accounted for and running, the auctioneer runs the method run_auction(). This includes a "game loop" that keeps going until one of the bots wins or the round limit is reached (usually 200 rounds).

Each round of the auction, the auctioneer performs the following process:
	- __start_round(). Prints a message to the screen, and sets all bids to zero. 
	- __collect_bids(). Asks each of the bots for their bid on the current round.
	- __pick_winner_of_the_round(). Chooses a winning bid and awards the painting.
	- __update_scores(). Updates the scores for each bot. 
	- __export_data(). Exports a log of the auction run to a csv file. 
	- __check_end_conditions(). Checks if the auction should keep going or finish

#### Winners
__get_winners() determines the winners of the auction. If more than one bot has the same top score then all bots with that score win. 
The winners are returned with the run_auction method call.
