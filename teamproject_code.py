from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)
import asyncio

# =============================================
TOKEN = "8706021770:AAGKy5KvPJb3r0R0ZAKystRfp77FXzx70dk"
# =============================================

CHOOSE_SPORT, CHOOSE_TEAMS, CHOOSE_PLAYERS_PER_TEAM, WAIT_SESSION_INFO = range(4)

SPORTS = {
    "football":   "Футбол",
    "basketball": "Баскетбол",
    "volleyball": "Волейбол",
    "cs2":        "CS2",
}
SPORT_EMOJI = {
    "football": "⚽", "basketball": "🏀", "volleyball": "🏐", "cs2": "🎮",
}
TEAM_COLORS = ["🔴", "🔵", "🟢", "🟡"]

# sessions[chat_id] = {sport, num_teams, players_per_team, time, place, players}
sessions = {}
# ratings[chat_id][sport][name] = {"total": int, "count": int}
ratings = {}
# rating_state[user_id] = {group_chat_id, players_to_rate, current, given_ratings}
rating_state = {}
# all_players[chat_id] = set of all player names ever added
all_players = {}


# ─── Helper functions ────────────────────────────────────────────────────────

def get_chat_ratings(chat_id):
    """Return the ratings dict for a given chat, initialising it if needed."""
    if chat_id not in ratings:
        ratings[chat_id] = {sport: {} for sport in SPORTS}
    return ratings[chat_id]


def get_chat_all_players(chat_id):
    """Return the set of all players ever added in a given chat."""
    if chat_id not in all_players:
        all_players[chat_id] = set()
    return all_players[chat_id]


def get_rating(chat_id, sport, name):
    """
    Return the average rating of a player for a specific sport in a chat.
    Returns None if the player has no ratings yet.
    """
    r = get_chat_ratings(chat_id)
    if name in r[sport] and r[sport][name]["count"] > 0:
        return r[sport][name]["total"] / r[sport][name]["count"]
    return None


def team_avg(chat_id, sport, team):
    """
    Calculate and return the average rating of a team as a formatted string.
    Returns 'N/A' if no players in the team have ratings.
    """
    vals = [get_rating(chat_id, sport, n) for n in team if get_rating(chat_id, sport, n)]
    if not vals:
        return "N/A"
    return f"⭐ {sum(vals)/len(vals):.1f}"


async def send_temp(message, text, delay=6, reply_markup=None, delete_original=True):
    """
    Send a temporary message that auto-deletes after `delay` seconds.
    Optionally also deletes the original user command message.
    """
    sent = await message.reply_text(text, reply_markup=reply_markup)
    await asyncio.sleep(delay)
    try:
        await sent.delete()
        if delete_original:
            await message.delete()
    except Exception:
        pass


# ─── Conversation: setup flow ─────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point for the bot.
    - If called with 'rate_<chat_id>' argument (from /rate button), begins
      the private rating flow for that group session.
    - Otherwise, shows sport selection keyboard to start a new session.
    """
    user_id = update.message.from_user.id

    if context.args and context.args[0].startswith("rate_"):
        group_chat_id = int(context.args[0].replace("rate_", ""))
        if group_chat_id not in sessions or not sessions[group_chat_id]["players"]:
            await update.message.reply_text("Сессия не найдена. Попробуй ещё раз.")
            return
        rating_state[user_id] = {
            "group_chat_id":   group_chat_id,
            "players_to_rate": sessions[group_chat_id]["players"][:],
            "current":         0,
            "given_ratings":   {}
        }
        await ask_next_rating(update.message, user_id)
        return

    keyboard = [
        [InlineKeyboardButton(f"{SPORT_EMOJI[k]} {v}", callback_data=f"sport_{k}")]
        for k, v in SPORTS.items()
    ]
    sent = await update.message.reply_text(
        "Привет! Я помогу разделить вас на команды.\n\nВыбери вид спорта:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data["setup_msg_id"]  = sent.message_id
    context.user_data["setup_chat_id"] = sent.chat_id
    asyncio.create_task(update.message.delete())
    return CHOOSE_SPORT


async def choose_sport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle sport selection callback and ask for number of teams."""
    query = update.callback_query
    await query.answer()
    sport_key = query.data.replace("sport_", "")
    chat_id   = query.message.chat_id

    sessions[chat_id] = {
        "sport": sport_key, "num_teams": 2,
        "players_per_team": None, "time": None,
        "place": None, "players": []
    }
    label = f"{SPORT_EMOJI[sport_key]} {SPORTS[sport_key]}"
    keyboard = [[
        InlineKeyboardButton("2 команды", callback_data="teams_2"),
        InlineKeyboardButton("3 команды", callback_data="teams_3"),
        InlineKeyboardButton("4 команды", callback_data="teams_4"),
    ]]
    await query.edit_message_text(
        f"Выбран спорт: {label}\n\nСколько команд?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_TEAMS


async def choose_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team count selection callback and ask for players per team."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    num = int(query.data.replace("teams_", ""))
    sessions[chat_id]["num_teams"] = num
    await query.edit_message_text(
        f"Команд: {num}\n\nСколько игроков в каждой команде? (напиши число)"
    )
    return CHOOSE_PLAYERS_PER_TEAM


async def choose_players_per_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receive the number of players per team from the user.
    Validates that the input is a positive integer, then asks for time and place.
    """
    chat_id = update.message.chat_id
    text    = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("Напиши целое число, например: 5")
        return CHOOSE_PLAYERS_PER_TEAM
    sessions[chat_id]["players_per_team"] = int(text)
    num = sessions[chat_id]["num_teams"]
    ppt = int(text)
    asyncio.create_task(update.message.delete())
    await update.message.reply_text(
        f"Команд: {num}  |  В команде: {ppt}  |  Всего: ~{num*ppt}\n\n"
        "Напиши время и место через запятую:\n"
        "Пример: 18:00, Стадион МНУ"
    )
    return WAIT_SESSION_INFO


async def create_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Finalise session creation by saving time and place.
    Deletes the setup inline keyboard message and shows a temporary confirmation.
    Expected input format: 'HH:MM, Place name'
    """
    chat_id = update.message.chat_id
    if chat_id not in sessions:
        await update.message.reply_text("Сначала выбери спорт через /start")
        return ConversationHandler.END
    parts = update.message.text.strip().split(",", 1)
    if len(parts) < 2:
        await update.message.reply_text("Неверный формат. Напиши:\n18:00, Стадион МНУ")
        return WAIT_SESSION_INFO
    sessions[chat_id]["time"]  = parts[0].strip()
    sessions[chat_id]["place"] = parts[1].strip()
    s = sessions[chat_id]
    label = f"{SPORT_EMOJI[s['sport']]} {SPORTS[s['sport']]}"

    setup_msg_id  = context.user_data.get("setup_msg_id")
    setup_chat_id = context.user_data.get("setup_chat_id")
    if setup_msg_id:
        try:
            await context.bot.delete_message(chat_id=setup_chat_id, message_id=setup_msg_id)
        except Exception:
            pass

    asyncio.create_task(update.message.delete())
    await send_temp(update.message,
        f"Сессия создана!\n\n"
        f"Спорт: {label}\n"
        f"Время: {s['time']}\n"
        f"Место: {s['place']}\n"
        f"Команд: {s['num_teams']}  |  В команде: {s['players_per_team']}\n\n"
        "/join Алихан\n"
        "/join Алихан, Бекзат, Нурлан\n\n"
        "/players — список\n"
        "/shuffle — разделить",
        delay=8, delete_original=False
    )
    return ConversationHandler.END


# ─── Player management ────────────────────────────────────────────────────────

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Add one or more players to the current session.
    Supports comma-separated names: /join Ali, Bekzat, Nulan
    Confirmation message auto-deletes after 4 seconds.
    """
    chat_id = update.message.chat_id
    if chat_id not in sessions or sessions[chat_id]["time"] is None:
        await update.message.reply_text("Сначала создай сессию через /start")
        return
    if not context.args:
        await update.message.reply_text("Напиши имя: /join Алихан")
        return
    raw   = " ".join(context.args)
    names = [n.strip() for n in raw.split(",") if n.strip()]
    added, skipped = [], []
    for name in names:
        if name in sessions[chat_id]["players"]:
            skipped.append(name)
        else:
            sessions[chat_id]["players"].append(name)
            get_chat_all_players(chat_id).add(name)
            added.append(name)
    count = len(sessions[chat_id]["players"])
    if added:
        sent = await update.message.reply_text(f"{', '.join(added)} добавлен(ы)! Всего: {count}")
        await asyncio.sleep(4)
        try:
            await sent.delete()
            await update.message.delete()
        except Exception:
            pass
    if skipped:
        warn = await update.message.reply_text(f"Уже в списке: {', '.join(skipped)}")
        await asyncio.sleep(4)
        try:
            await warn.delete()
        except Exception:
            pass


async def players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the current session's player list with their average ratings."""
    chat_id = update.message.chat_id
    if chat_id not in sessions or not sessions[chat_id]["players"]:
        await update.message.reply_text("Список пуст. Добавь через /join Имя")
        return
    sport = sessions[chat_id]["sport"]
    lines = []
    for i, name in enumerate(sessions[chat_id]["players"], 1):
        avg   = get_rating(chat_id, sport, name)
        r_str = f"⭐ {avg:.1f}" if avg else "нет рейтинга"
        lines.append(f"{i}. {name} — {r_str}")
    await update.message.reply_text(
        "Игроки:\n" + "\n".join(lines) +
        f"\n\nВсего: {len(sessions[chat_id]['players'])} чел."
    )


async def show_all_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show all players who have ever joined a session in this chat,
    along with their ratings per sport.
    """
    chat_id = update.message.chat_id
    ap = get_chat_all_players(chat_id)
    if not ap:
        await update.message.reply_text("Ещё никто не играл.")
        return
    lines = []
    for name in sorted(ap):
        parts = []
        for sk in SPORTS:
            avg = get_rating(chat_id, sk, name)
            if avg:
                parts.append(f"{SPORT_EMOJI[sk]} ⭐ {avg:.1f}")
        r_str = " | ".join(parts) if parts else "нет рейтинга"
        lines.append(f"{name} ({r_str})")
    await update.message.reply_text(
        f"Все игроки этого чата ({len(ap)} чел.):\n\n" + "\n".join(lines)
    )


# ─── Shuffle ──────────────────────────────────────────────────────────────────

async def shuffle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Divide players into balanced teams using a snake-draft algorithm.
    Players are sorted by rating (descending) then distributed in a
    zigzag pattern so strong players end up on different teams.
    Players without ratings are treated as average (5.0).
    Handles uneven player counts by distributing extras across teams.
    """
    chat_id = update.message.chat_id
    if chat_id not in sessions or not sessions[chat_id]["players"]:
        await update.message.reply_text("Нет игроков. Добавь через /join Имя")
        return
    s           = sessions[chat_id]
    player_list = s["players"][:]
    sport       = s["sport"]
    num_teams   = s["num_teams"]
    if len(player_list) < num_teams:
        await update.message.reply_text(f"Нужно минимум {num_teams} игрока(ов)!")
        return

    sorted_players = sorted(
        player_list,
        key=lambda n: get_rating(chat_id, sport, n) or 5.0,
        reverse=True
    )
    teams   = [[] for _ in range(num_teams)]
    indices = list(range(num_teams)) + list(range(num_teams - 1, -1, -1))
    cycle   = []
    while len(cycle) < len(sorted_players):
        cycle.extend(indices)
    for i, name in enumerate(sorted_players):
        teams[cycle[i]].append(name)

    label = f"{SPORT_EMOJI[sport]} {SPORTS[sport]}"
    lines = [f"{label}  |  {s['time']}  |  {s['place']}\nИгроков в команде: {s['players_per_team']}\n"]
    for i, team in enumerate(teams):
        avg     = team_avg(chat_id, sport, team)
        members = "\n".join(
            f"  {n} ({f'⭐ {get_rating(chat_id, sport, n):.1f}' if get_rating(chat_id, sport, n) else 'нет рейт.'})"
            for n in team
        )
        lines.append(f"{TEAM_COLORS[i]} Команда {i+1} (avg {avg}):\n{members}")
    extra = len(player_list) % num_teams
    if extra:
        lines.append(f"\n⚠️ Лишних игроков: {extra} (распределены по командам)")
    lines.append("\nПосле матча: /rate")
    await update.message.reply_text("\n\n".join(lines))


# ─── Rating system ────────────────────────────────────────────────────────────

async def rate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Send a button in the group chat that redirects each user to
    the bot's private chat to rate players individually.
    The button message auto-deletes after 30 seconds.
    """
    chat_id = update.message.chat_id
    if chat_id not in sessions or not sessions[chat_id]["players"]:
        await update.message.reply_text("Нет игроков для оценки.")
        return
    bot_username = (await context.bot.get_me()).username
    keyboard = [[InlineKeyboardButton(
        "⭐ Оценить игроков в личке",
        url=f"https://t.me/{bot_username}?start=rate_{chat_id}"
    )]]
    await send_temp(update.message,
        "Матч завершён! Нажми кнопку — оценишь игроков в личном чате:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        delay=30, delete_original=True
    )


async def ask_next_rating(message, user_id):
    """
    Send the next player rating prompt (1–10 inline buttons) to the user in DM.
    If all players have been rated, calls save_ratings_and_finish.
    """
    state = rating_state[user_id]
    idx   = state["current"]
    total = len(state["players_to_rate"])
    if idx >= total:
        await save_ratings_and_finish(message, user_id)
        return
    name = state["players_to_rate"][idx]
    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"rate_{i}") for i in range(1, 6)],
        [InlineKeyboardButton(str(i), callback_data=f"rate_{i}") for i in range(6, 11)],
    ]
    await message.reply_text(
        f"{idx+1}/{total} — {name}\n(1 плохо → 10 отлично)",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle a rating button press in private chat.
    Saves the score, auto-deletes the message after 2 seconds,
    then shows the next player to rate.
    """
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in rating_state:
        await query.edit_message_text("Начни оценку заново — нажми кнопку в группе.")
        return
    score = int(query.data.replace("rate_", ""))
    state = rating_state[user_id]
    name  = state["players_to_rate"][state["current"]]
    state["given_ratings"][name] = score
    state["current"] += 1
    await query.edit_message_text(f"{name}: {score}/10")
    await asyncio.sleep(2)
    try:
        await query.message.delete()
    except Exception:
        pass
    await ask_next_rating(query.message, user_id)


async def save_ratings_and_finish(message, user_id):
    """
    Persist all collected ratings into the chat's ratings dict.
    Ratings are stored per-chat and per-sport so they don't mix.
    Sends a confirmation to the user in private chat.
    """
    state         = rating_state[user_id]
    group_chat_id = state["group_chat_id"]
    sport         = sessions[group_chat_id]["sport"]
    sport_label   = f"{SPORT_EMOJI[sport]} {SPORTS[sport]}"
    r             = get_chat_ratings(group_chat_id)
    for name, score in state["given_ratings"].items():
        if name not in r[sport]:
            r[sport][name] = {"total": 0, "count": 0}
        r[sport][name]["total"] += score
        r[sport][name]["count"] += 1
    await message.reply_text(
        f"Готово! Рейтинги сохранены для {sport_label}.\n"
        "Обновлённый список: /players в группе."
    )
    del rating_state[user_id]


# ─── Utility commands ─────────────────────────────────────────────────────────

async def clear_ratings_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for confirmation before clearing all ratings and player history for this chat."""
    keyboard = [[
        InlineKeyboardButton("Да, стереть", callback_data="confirm_clear"),
        InlineKeyboardButton("Отмена",      callback_data="cancel_clear"),
    ]]
    await send_temp(update.message,
        "Стереть все рейтинги и список игроков этого чата?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        delay=15, delete_original=True
    )


async def clear_ratings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the confirm/cancel buttons for clearing ratings."""
    query   = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    if query.data == "confirm_clear":
        ratings[chat_id]     = {sport: {} for sport in SPORTS}
        all_players[chat_id] = set()
        await query.edit_message_text("Рейтинги и история стёрты.")
    else:
        await query.edit_message_text("Отменено.")
    await asyncio.sleep(4)
    try:
        await query.message.delete()
    except Exception:
        pass


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a player's average rating across all sports in this chat."""
    chat_id = update.message.chat_id
    if not context.args:
        await update.message.reply_text("Напиши имя: /stats Алихан")
        return
    name  = " ".join(context.args).strip()
    lines = [f"Статистика: {name}\n"]
    found = False
    for sk, sl in SPORTS.items():
        avg = get_rating(chat_id, sk, name)
        if avg:
            cnt = get_chat_ratings(chat_id)[sk][name]["count"]
            lines.append(f"{SPORT_EMOJI[sk]} {sl}: ⭐ {avg:.1f} ({cnt} матч.)")
            found = True
    if not found:
        lines.append("Нет данных — игрок ещё не оценивался.")
    await update.message.reply_text("\n".join(lines))


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset the current session (clears players and session info, keeps ratings)."""
    chat_id = update.message.chat_id
    if chat_id in sessions:
        del sessions[chat_id]
    await send_temp(update.message, "Сессия сброшена. Начни заново через /start", delay=5)
    return ConversationHandler.END


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    """Register all handlers and start the bot with long polling."""
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_SPORT:            [CallbackQueryHandler(choose_sport,            pattern="^sport_")],
            CHOOSE_TEAMS:            [CallbackQueryHandler(choose_teams,            pattern="^teams_")],
            CHOOSE_PLAYERS_PER_TEAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_players_per_team)],
            WAIT_SESSION_INFO:       [MessageHandler(filters.TEXT & ~filters.COMMAND, create_session)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("join",          join))
    app.add_handler(CommandHandler("players",       players))
    app.add_handler(CommandHandler("all_players",   show_all_players))
    app.add_handler(CommandHandler("shuffle",       shuffle))
    app.add_handler(CommandHandler("rate",          rate_start))
    app.add_handler(CommandHandler("stats",         stats))
    app.add_handler(CommandHandler("clear_ratings", clear_ratings_ask))
    app.add_handler(CommandHandler("reset",         reset))
    app.add_handler(CallbackQueryHandler(rate_callback,          pattern="^rate_"))
    app.add_handler(CallbackQueryHandler(clear_ratings_callback, pattern="^(confirm|cancel)_clear$"))

    print("Бот запущен! Нажми Ctrl+C чтобы остановить.")
    app.run_polling()


if __name__ == "__main__":
    main()