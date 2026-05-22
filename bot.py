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

# ---------------- NORMALIZE QUANTITY ---------------- #

def normalize_quantity(quantity, readable):
    try:
        qty = int(quantity)
    except:
        return quantity

    # Do NOT modify distance challenges
    if "Distance" in readable:
        return qty

    # Money stored as cents
    if "Money made" in readable:
        return qty // 100

    # Time based challenges (milliseconds)
    if qty >= 100000:
        return 1

    return qty

# ---------------- DATE FORMAT ---------------- #

def ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    return str(n) + suffix

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
        response = requests.get(
            "https://rdo-dailies.com/",
            timeout=10
        )

        lang_response = requests.get(
            "https://rdo-dailies.com/website/languages/en.json",
            timeout=10
        )

        soup = BeautifulSoup(response.text, "html.parser")
        lang_data = lang_response.json()

        rows = soup.find_all("div", class_="rows")

        for row in rows:
            goal = row.find("p", class_="daily-goal")
            text = row.find("p", class_="daily-general")

            if not goal or not text:
                continue

            quantity = goal.text.strip() or goal.get("data-goal")
            key = text.get("data-text")

            if not quantity or not key:
                continue

            readable = lang_data.get(key, key)

            qty = normalize_quantity(quantity, readable)

            formatted = f"• {qty} {readable}"

            if key.startswith("mpgc_"):
                general.append(formatted)

            elif key.startswith("mprc_"):
                for role in roles:
                    if role in key:
                        roles[role].append(formatted)
                        break

        for role in roles:
            roles[role] = roles[role][:3]

    except Exception as e:
        print("Error fetching dailies:", e)

    return general, roles

# ---------------- EMBED ---------------- #

def build_embed(general, roles):
    now = datetime.datetime.now(IST)

    # Date formatting
    date_str = f"{ordinal(now.day)} {now.strftime('%b, %Y')}"

    # Next 11:32 IST timestamp
    next_post = IST.localize(datetime.datetime(
        now.year,
        now.month,
        now.day,
        11,
        32
    ))

    if now > next_post:
        next_post += datetime.timedelta(days=1)

    timestamp = int(next_post.timestamp())

    embed = discord.Embed(
        title=f"Daily Challenges ({date_str})",
        description=f"Rank 15+ Role Challenges\nPosts daily at <t:{timestamp}:t>",
        color=0x8B0000
    )

    if general:
        embed.add_field(
            name="🔘 General Challenges",
            value="\n".join(general)[:1024],
            inline=False
        )

    role_emojis = {
        "bounty": "🔴",
        "trader": "🟠",
        "collector": "🟤",
        "moonshiner": "🟣",
        "naturalist": "🟢"
    }

    for role, challenges in roles.items():
        if challenges:
            embed.add_field(
                name=f"{role_emojis.get(role)} {role.capitalize()}",
                value="\n".join(challenges)[:1024],
                inline=False
            )

    embed.set_footer(text="Built for the people by T00R.")

    return embed

# ---------------- EVENTS ---------------- #

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")

    except Exception as e:
        print("Slash command sync failed:", e)

    # Prevent task loop from starting twice
    if not auto_post.is_running():
        auto_post.start()
        print("Auto-post loop started.")

# ---------------- SLASH COMMANDS ---------------- #

@bot.tree.command(
    name="dailies",
    description="Fetch today's RDO daily challenges (Rank 15+)"
)
async def dailies(interaction: discord.Interaction):
    general, roles = fetch_dailies()

    embed = build_embed(general, roles)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(
    name="setdailychannel",
    description="Set this channel for automatic daily posts"
)
async def setdailychannel(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You need Manage Server permission to use this command.",
            ephemeral=True
        )
        return

    config = load_config()

    config[str(interaction.guild.id)] = interaction.channel.id

    save_config(config)

    await interaction.response.send_message(
        f"Daily auto-post channel set to {interaction.channel.mention}",
        ephemeral=True
    )

# ---------------- AUTO POST ---------------- #

@auto_post.before_loop
async def before_auto_post():
    await bot.wait_until_ready()

@tasks.loop(minutes=1)
async def auto_post():
    now = datetime.datetime.now(IST)

    print(f"Checking schedule: {now.strftime('%H:%M:%S')}")

    if now.hour == 11 and now.minute == 32:

        print("Posting dailies...")

        config = load_config()

        for guild_id, channel_id in config.items():

            guild = bot.get_guild(int(guild_id))

            if not guild:
                print(f"Guild not found: {guild_id}")
                continue

            channel = guild.get_channel(channel_id)

            if not channel:
                print(f"Channel not found: {channel_id}")
                continue

            try:
                general, roles = fetch_dailies()

                embed = build_embed(general, roles)

                await channel.send(embed=embed)

                print(
                    f"Successfully posted in "
                    f"{guild.name} -> #{channel.name}"
                )

            except Exception as e:
                print(
                    f"Failed posting in guild "
                    f"{guild_id}: {e}"
                )

# ---------------- STARTUP ---------------- #

if __name__ == "__main__":

    web_thread = threading.Thread(target=run_web)
    web_thread.start()

    if not TOKEN:
        print("ERROR: DISCORD_TOKEN is not set.")
        exit(1)

    bot.run(TOKEN)
