"""
Discord bot with five useful slash commands.

Commands:
    /ping                    – check the bot's latency
    /poll <question> [...]   – poll with reaction buttons (up to 10 options)
    /weather <city>          – current weather via the free Open-Meteo API (no API key needed)
    /userinfo [user]         – info about a server member
Event:
    on_member_join           – greets new members automatically

All configuration comes from environment variables (see .env.example) so the
bot token never ends up in the code.

Start:
    python bot.py
"""

from __future__ import annotations

import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load .env (token & optional settings)
load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()

# Optional: test server ID -> slash commands show up INSTANTLY there.
# Without GUILD_ID the commands are registered globally (can take up to 1 hour).
GUILD_ID = os.getenv("GUILD_ID", "").strip()

# Optional: channel ID for welcome messages. Without it the server's
# system channel is used.
WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID", "").strip()

# Emojis for poll options (index 0 = option 1, etc.)
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

# Map Open-Meteo weather codes to readable text (subset of WMO codes)
WEATHER_CODES = {
    0: "☀️ Clear sky",
    1: "🌤️ Mainly clear",
    2: "⛅ Partly cloudy",
    3: "☁️ Overcast",
    45: "🌫️ Fog",
    48: "🌫️ Depositing rime fog",
    51: "🌦️ Light drizzle",
    53: "🌦️ Drizzle",
    55: "🌧️ Heavy drizzle",
    61: "🌦️ Light rain",
    63: "🌧️ Rain",
    65: "🌧️ Heavy rain",
    71: "🌨️ Light snow",
    73: "🌨️ Snow",
    75: "❄️ Heavy snow",
    80: "🌦️ Light rain showers",
    81: "🌧️ Rain showers",
    82: "⛈️ Violent rain showers",
    95: "⛈️ Thunderstorm",
    96: "⛈️ Thunderstorm with hail",
    99: "⛈️ Severe thunderstorm with hail",
}


# --- Intents & bot object ---------------------------------------------------

# The "members" intent is needed for on_member_join and /userinfo (join date).
# It is a privileged intent and must be enabled in the Discord Developer
# Portal (see README).
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# --- Helper: fetch JSON from an API (async) ---------------------------------

async def fetch_json(url: str, params: dict) -> dict | None:
    """Fetch JSON from a URL. Returns None if something goes wrong."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except (aiohttp.ClientError, TimeoutError):
        return None


# --- Lifecycle --------------------------------------------------------------

@bot.event
async def setup_hook() -> None:
    """Runs once at startup: registers the slash commands."""
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"[SYNC] Registered {len(synced)} commands on test server {GUILD_ID} (available immediately).")
    else:
        synced = await bot.tree.sync()
        print(f"[SYNC] Registered {len(synced)} commands globally (can take up to 1 hour).")


@bot.event
async def on_ready() -> None:
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"[READY] Active on {len(bot.guilds)} server(s).")


@bot.event
async def on_member_join(member: discord.Member) -> None:
    """Greets new members automatically."""
    # Determine the target channel: configured channel OR the server's system channel
    channel = None
    if WELCOME_CHANNEL_ID:
        channel = member.guild.get_channel(int(WELCOME_CHANNEL_ID))
    if channel is None:
        channel = member.guild.system_channel
    if channel is None:
        return  # no suitable channel found

    embed = discord.Embed(
        title="👋 Welcome!",
        description=f"Hi {member.mention}, glad you joined **{member.guild.name}**!",
        color=discord.Color.green(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"You are member #{member.guild.member_count}")
    await channel.send(embed=embed)


# --- /ping ------------------------------------------------------------------

@bot.tree.command(name="ping", description="Shows the bot's current latency.")
async def ping(interaction: discord.Interaction) -> None:
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! Latency: **{latency_ms} ms**")


# --- /poll ------------------------------------------------------------------

@bot.tree.command(name="poll", description="Creates a poll with reaction buttons.")
@app_commands.describe(
    question="The poll question",
    options="Comma-separated answer options (leave empty for Yes/No)",
)
async def poll(interaction: discord.Interaction, question: str, options: str = "") -> None:
    # Prepare the options from the comma-separated list
    choices = [o.strip() for o in options.split(",") if o.strip()]

    if len(choices) > 10:
        await interaction.response.send_message(
            "⚠️ A maximum of 10 options is allowed.", ephemeral=True
        )
        return

    embed = discord.Embed(title="📊 Poll", description=f"**{question}**", color=discord.Color.blurple())

    if choices:
        # Multiple options -> numbered list + number emojis
        lines = [f"{NUMBER_EMOJIS[i]} {choice}" for i, choice in enumerate(choices)]
        embed.add_field(name="Options", value="\n".join(lines), inline=False)
        reactions = NUMBER_EMOJIS[: len(choices)]
    else:
        # No options -> simple Yes/No poll
        embed.add_field(name="Options", value="👍 Yes\n👎 No", inline=False)
        reactions = ["👍", "👎"]

    embed.set_footer(text=f"Poll by {interaction.user.display_name}")

    # Send the message and then add the reactions
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    for emoji in reactions:
        await message.add_reaction(emoji)


# --- /weather ---------------------------------------------------------------

@bot.tree.command(name="weather", description="Shows the current weather for a city.")
@app_commands.describe(city="City name, e.g. Berlin")
async def weather(interaction: discord.Interaction, city: str) -> None:
    # The response may take a moment (two API calls) -> Discord shows "thinking"
    await interaction.response.defer()

    # 1) City -> coordinates (Open-Meteo geocoding, no API key)
    geo = await fetch_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": city, "count": 1, "language": "en", "format": "json"},
    )
    if not geo or not geo.get("results"):
        await interaction.followup.send(f"❌ City **{city}** not found.")
        return

    place = geo["results"][0]
    lat, lon = place["latitude"], place["longitude"]
    name = place["name"]
    country = place.get("country", "")

    # 2) Coordinates -> current weather
    data = await fetch_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
        },
    )
    if not data or "current" not in data:
        await interaction.followup.send("❌ Could not fetch weather data.")
        return

    current = data["current"]
    code = current.get("weather_code", -1)
    condition = WEATHER_CODES.get(code, "Unknown")

    embed = discord.Embed(
        title=f"🌍 Weather in {name}, {country}",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Condition", value=condition, inline=False)
    embed.add_field(name="🌡️ Temperature", value=f"{current['temperature_2m']} °C", inline=True)
    embed.add_field(name="💧 Humidity", value=f"{current['relative_humidity_2m']} %", inline=True)
    embed.add_field(name="💨 Wind", value=f"{current['wind_speed_10m']} km/h", inline=True)
    embed.set_footer(text="Data source: open-meteo.com")

    await interaction.followup.send(embed=embed)


# --- /userinfo --------------------------------------------------------------

@bot.tree.command(name="userinfo", description="Shows information about a member.")
@app_commands.describe(user="The member (leave empty for yourself)")
async def userinfo(interaction: discord.Interaction, user: discord.Member | None = None) -> None:
    member = user or interaction.user

    embed = discord.Embed(title=f"👤 {member.display_name}", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Username", value=str(member), inline=True)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(
        name="Account created",
        value=discord.utils.format_dt(member.created_at, style="D"),
        inline=False,
    )
    if member.joined_at:
        embed.add_field(
            name="Joined server",
            value=discord.utils.format_dt(member.joined_at, style="D"),
            inline=False,
        )
    # List roles without @everyone
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    embed.add_field(
        name=f"Roles ({len(roles)})",
        value=" ".join(roles) if roles else "none",
        inline=False,
    )

    await interaction.response.send_message(embed=embed)


# --- Start ------------------------------------------------------------------

def main() -> None:
    if not TOKEN:
        print("[ERROR] DISCORD_BOT_TOKEN is missing. Create a .env file (see .env.example).")
        raise SystemExit(1)
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
