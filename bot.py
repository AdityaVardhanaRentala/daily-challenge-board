import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
import json
import os
import datetime
import pytz
from flask import Flask
import threading

# ---------------- WEB SERVER FOR RENDER ---------------- #

app = Flask(__name__)

@app.route("/")
def home():
    return "Daily Challenge Board is alive."

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ---------------- DISCORD BOT SETUP ---------------- #

TOKEN = os.getenv("DISCORD_TOKEN")
CONFIG_FILE = "config.json"
IST = pytz.timezone("Asia/Kolkata")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- CONFIG ---------------- #

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

# ---------------- FORMAT QUANTITY ---------------- #

def format_quantity(quantity, readable):
    qty = int(quantity)

    if "Money made" in readable:
        qty = qty // 100

    if qty > 100000:
        qty = 1

    if any(word.isdigit() for word in readable.split()):
        return f"• {readable}"
    else:
        return f"• {qty} {readable}"

# ---------------- FETCH DAILIES ---------------- #

def fetch_dailies():
    general = []
    roles = {
        "bounty": [],
        "trader": [],
        "collector": [],
        "moonshiner": [],
        "naturalist": []
    }

    try:
        response = requests.get("https://rdo-dailies.com/", timeout=10)
        lang_response = requests.get(
            "https://rdo-dailies.com/website/languages/en.json",
            timeout=10
        )

        soup = BeautifulSoup(response.text, "html.parser")
        lang_data = lang_response.json()

        containers = soup.find_all("div", class_="daily-container")

        for index, container in enumerate(containers):
            rows = container.find_all("div", class_="rows")
            formatted_rows = []

            for row in rows:
                goal = row.find("p", class_="daily-goal")
                text = row.find("p", class_="daily-general")

                if not goal or not text:
                    continue

                quantity = goal.get("data-goal")
                key = text.get("data-text")

                if not quantity or not key:
                    continue

                readable = lang_data.get(key, key)
                formatted = format_quantity(quantity, readable)
                formatted_rows.append(formatted)

            if index == 0:
                general = formatted_rows
            elif index == 1:
                roles["bounty"] = formatted_rows[:3]
            elif index == 2:
                roles["trader"] = formatted_rows[:3]
            elif index == 3:
                roles["collector"] = formatted_rows[:3]
            elif index == 4:
                roles["moonshiner"] = formatted_rows[:3]
            elif index == 5:
                roles["naturalist"] = formatted_rows[:3]

    except Exception as e:
        print("Error fetching dailies:", e)

    return general, roles

# ---------------- EMBED ---------------- #

def build_embed(general, roles):
    embed = discord.Embed(
        title="Daily Challenges",
        description="Rank 15+ Role Challenges",
        color=0x8B0000
    )

    if general:
        embed.add_field(
            name="🟢 General Challenges",
            value="\n".join(general)[:1024],
            inline=False
        )

    role_emojis = {
        "bounty": "🟡",
        "trader": "🟠",
        "collector": "🟣",
        "moonshiner": "🔴",
        "naturalist": "🔵"
    }

    for role, challenges in roles.items():
        if challenges:
            embed.add_field(
                name=f"{role_emojis.get(role)} {role.capitalize()}",
                value="\n".join(challenges)[:1024],
                inline=False
            )

    embed.set_footer(text="Built for people by T00R.")
    return embed

# ---------------- EVENTS ---------------- #

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()
    auto_post.start()

# ---------------- COMMAND ---------------- #

@bot.tree.command(name="dailies", description="Fetch today's RDO daily challenges (Rank 15+)")
async def dailies(interaction: discord.Interaction):
    general, roles = fetch_dailies()
    embed = build_embed(general, roles)
    await interaction.response.send_message(embed=embed)

# ---------------- AUTO POST ---------------- #

@tasks.loop(minutes=1)
async def auto_post():
    now = datetime.datetime.now(IST)

    if now.hour == 11 and now.minute == 31:
        config = load_config()

        for guild_id, channel_id in config.items():
            guild = bot.get_guild(int(guild_id))
            if not guild:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            general, roles = fetch_dailies()
            embed = build_embed(general, roles)
            await channel.send(embed=embed)

# ---------------- STARTUP ---------------- #

if __name__ == "__main__":
    web_thread = threading.Thread(target=run_web)
    web_thread.start()

    if not TOKEN:
        print("ERROR: DISCORD_TOKEN is not set.")
        exit(1)

    bot.run(TOKEN)
