Khandomizer Bot 
A Telegram bot for organizing team sports games. Create a session, add players, and the bot automatically splits them into balanced teams based on player ratings.
Features
Choose from 4 sports: Football, Basketball, Volleyball, CS2
Split into 2, 3, or 4 teams
Rating-based shuffle — strong players are distributed across different teams (snake-draft algorithm)
Post-match player rating via private chat (no group spam)
Per-sport rating history, separate for each chat
Auto-deleting setup messages to keep the chat clean
Commands
Command	Description
`/start`	Choose sport and create a session
`/join Name`	Add a player (comma-separated for multiple)
`/players`	Show current session players with ratings
`/all_players`	Show all players ever added in this chat
`/shuffle`	Split players into balanced teams
`/rate`	Rate players after a match (opens in DM)
`/stats Name`	Show a player's stats across all sports
`/clear_ratings`	Erase all ratings and player history for this chat
`/reset`	Reset the current session
Setup
1. Clone the repository
```bash
git clone https://github.com/alikhanabdimanat-netizen/khandomizer_bot.git
cd khandomizer_bot
```
2. Install dependencies
```bash
pip install -r requirements.txt
```
3. Get a Bot Token
Open Telegram and find `@BotFather`
Send `/newbot` and follow the instructions
Copy the token you receive
4. Add your token
Open `bot.py` and replace the placeholder on line 9:
```python
TOKEN = "8706021770:AAGKy5KvPJb3r0R0ZAKystRfp77FXzx70dk"
```
5. Run the bot
```bash
python bot.py
```
How it works
Run `/start` in a group chat → select sport → number of teams → players per team → time and place
Players join with `/join Name`
Run `/shuffle` — the bot sorts players by rating and distributes them using a snake-draft so the strongest players end up on different teams
After the match, run `/rate` — each user taps the button and rates others privately
Ratings are saved per sport per chat and used in all future shuffles
Dependencies
Python 3.10+
`python-telegram-bot` 20.7
Notes
All data is stored in memory and resets when the bot restarts
Ratings are isolated per chat — different groups have separate rating histories
