"""
Discord bot for the LoL Jungle Coach.

Usage:
    python app/discord_bot.py

Setup:
    1. Create a Discord bot at https://discord.com/developers/applications
    2. Enable MESSAGE CONTENT intent
    3. Add bot to your server with Send Messages + Attach Files permissions
    4. Set DISCORD_BOT_TOKEN in .env
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import discord
from discord import app_commands
import config
from llm_client import analyze_screenshot, ask_question


intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tree.command(name="coach", description="Analyze a game screenshot and get coaching advice")
@app_commands.describe(
    screenshot="Upload a game screenshot",
    question="What do you want to know? (default: What should I do here?)",
)
async def coach_command(
    interaction: discord.Interaction,
    screenshot: discord.Attachment,
    question: str = "What should I do here?",
):
    await interaction.response.defer(thinking=True)

    try:
        image_bytes = await screenshot.read()
        advice = analyze_screenshot(image_bytes, question)

        # Discord has a 2000 char limit per message
        if len(advice) > 1900:
            # Split into chunks
            parts = [advice[i:i+1900] for i in range(0, len(advice), 1900)]
            await interaction.followup.send(parts[0])
            for part in parts[1:]:
                await interaction.channel.send(part)
        else:
            await interaction.followup.send(advice)

    except Exception as e:
        await interaction.followup.send(f"Error analyzing screenshot: {e}")


@tree.command(name="ask", description="Ask a jungle coaching question")
@app_commands.describe(question="Your jungle coaching question")
async def ask_command(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)

    try:
        advice = ask_question(question)

        if len(advice) > 1900:
            parts = [advice[i:i+1900] for i in range(0, len(advice), 1900)]
            await interaction.followup.send(parts[0])
            for part in parts[1:]:
                await interaction.channel.send(part)
        else:
            await interaction.followup.send(advice)

    except Exception as e:
        await interaction.followup.send(f"Error: {e}")


@client.event
async def on_ready():
    await tree.sync()
    print(f"Bot is ready! Logged in as {client.user}")
    print(f"Invite URL: https://discord.com/api/oauth2/authorize?client_id={client.user.id}&permissions=2048&scope=bot%20applications.commands")


@client.event
async def on_message(message: discord.Message):
    """Handle screenshot uploads in chat without slash commands."""
    if message.author == client.user:
        return

    # If someone posts an image with a question
    if message.attachments and message.content:
        attachment = message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith("image/"):
            async with message.channel.typing():
                image_bytes = await attachment.read()
                advice = analyze_screenshot(image_bytes, message.content)

            if len(advice) > 1900:
                parts = [advice[i:i+1900] for i in range(0, len(advice), 1900)]
                for part in parts:
                    await message.reply(part)
            else:
                await message.reply(advice)


if __name__ == "__main__":
    if not config.DISCORD_BOT_TOKEN:
        print("DISCORD_BOT_TOKEN not set in .env")
        print("1. Create a bot at https://discord.com/developers/applications")
        print("2. Copy the token to your .env file")
        sys.exit(1)

    client.run(config.DISCORD_BOT_TOKEN)
