import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
import json
import os
import datetime
import pytz
from flask import Flask
from threading import Thread

# ---------------- WEB SERVER FOR RENDER ---------------- #

app = Flask(__name__)

@app.route("/")
def home():
    return "Daily Challenge Board is alive."

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web).start()

# ---------------- DISCORD BOT SETUP ---------------- #

TOKEN = os.getenv("DISCORD_TOKEN")
CONFIG_FILE = "config.json"
IST = pytz.timezone("Asia/Kolkata")

intents = discord.Intents.default()
intents.message_content = True
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

        rows = soup.find_all("div", class_="rows")

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
            formatted = f"• {quantity} {readable}"

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
                name=f"{role_emojis.get(role, '⚪')} {role.capitalize()}",
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

# ---------------- COMMANDS ---------------- #

@bot.tree.command(name="dailies", description="Fetch today's RDO daily challenges (Rank 15+)")
async def dailies(interaction: discord.Interaction):
    general, roles = fetch_dailies()
    embed = build_embed(general, roles)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="setdailychannel", description="Set this channel for daily auto-posting")
@commands.has_permissions(manage_guild=True)
async def setdailychannel(interaction: discord.Interaction):
    config = load_config()
    config[str(interaction.guild.id)] = interaction.channel.id
    save_config(config)

    await interaction.response.send_message(
        f"Daily auto-post channel set to {interaction.channel.mention}",
        ephemeral=True
    )

@setdailychannel.error
async def setdailychannel_error(interaction: discord.Interaction, error):
    if isinstance(error, commands.MissingPermissions):
        await interaction.response.send_message(
            "You need Manage Server permission to use this command.",
            ephemeral=True
        )

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

            general, roles = await bot.loop.run_in_executor(None, fetch_dailies)
            embed = build_embed(general, roles)

            await channel.send(embed=embed)

bot.run(TOKEN)

