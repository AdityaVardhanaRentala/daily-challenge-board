import discord
from discord.ext import commands, tasks
from playwright.async_api import async_playwright
import json
import os
import datetime
import pytz

import os
TOKEN = os.getenv("DISCORD_TOKEN")


CONFIG_FILE = "config.json"
IST = pytz.timezone("Asia/Kolkata")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------------- CONFIG MANAGEMENT ---------------- #

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)


# ---------------- FETCH DAILIES ---------------- #

async def fetch_dailies():
    general = []
    roles = {
        "bounty": [],
        "trader": [],
        "collector": [],
        "moonshiner": [],
        "naturalist": []
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://rdo-dailies.com/", timeout=60000)

        await page.wait_for_selector("div.rows", timeout=60000)
        rows = await page.query_selector_all("div.rows")

        for row in rows:
            goal_el = await row.query_selector("p.daily-goal")
            text_el = await row.query_selector("p.daily-general")

            if not goal_el or not text_el:
                continue

            quantity = (await goal_el.inner_text()).strip()
            text = (await text_el.inner_text()).strip()
            data_text = await text_el.get_attribute("data-text")

            if not quantity or not text or not data_text:
                continue

            formatted = f"• {quantity} {text}"

            if data_text.startswith("mpgc_"):
                general.append(formatted)

            elif data_text.startswith("mprc_"):
                for role in roles.keys():
                    if role in data_text:
                        roles[role].append(formatted)
                        break

        await browser.close()

    # Keep only first 3 role challenges (Rank 15+)
    for role in roles:
        roles[role] = roles[role][:3]

    return general, roles


# ---------------- EMBED BUILDER ---------------- #

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

    embed.set_footer(text="Built for the people by T00R.")
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
    await interaction.response.defer()

    general, roles = await fetch_dailies()
    embed = build_embed(general, roles)

    await interaction.followup.send(embed=embed)


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


# ---------------- AUTO POST TASK ---------------- #

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

            general, roles = await fetch_dailies()
            embed = build_embed(general, roles)

            await channel.send(embed=embed)


bot.run(TOKEN)
