import discord
from discord.ext import commands
from datetime import datetime
import os
import logging
from cogs.verification import VerificationView

async def setup(bot):
    @bot.tree.command(name="refresh", description="Refresh the welcome message")
    async def refresh_welcome(interaction: discord.Interaction):
        """Refresh the welcome message in the welcome channel"""
        try:
            # SECURITY: Check authorization
            from main import is_authorized_guild_or_owner
            if not is_authorized_guild_or_owner(interaction):
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ You are not authorized to use this command.", ephemeral=True
                    )
                return
            
            # SECURITY: Block DMs and check admin permissions
            if not interaction.guild:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
                return
            
            if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ You need Administrator permissions!", ephemeral=True)
                return
            
            # Get configuration from main.py
            from main import WELCOME_CHANNEL_ID, get_or_create_welcome_message
            
            # Get the welcome channel
            welcome_channel = interaction.guild.get_channel(WELCOME_CHANNEL_ID)
            if not welcome_channel:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Welcome channel not found!", ephemeral=True)
                return
            
            # Create welcome embed
            embed = discord.Embed(
                title="🎉 Welcome to The VoCreations Mentorship! 🎉",
                description=(
                    "You've officially joined a community designed to help you hit $10K/month with UGC — and we're not wasting time. On your onboarding call, we'll not only get your structure in place, but also start working on placing you with clients immediately.\n\n"
                    "But first… we need to learn about you.\n\n"
                    "👉 **Take the Onboarding Survey now to unlock access to the Discord.**\n\n"
                    "This survey ensures we understand your goals, current experience, and how to plug you into the mentorship the right way.\n\n"
                    "**No survey = no access.**"
                ),
                color=0xFFFFFF
            )
            embed.set_footer(text="Book Your Onboarding Call Today!")
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1370122090631532655/1401222798336200834/20.38.48_73b12891.jpg")
            
            # Use VerificationView
            try:
                msg = await get_or_create_welcome_message(welcome_channel, embed, VerificationView())
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"✅ Welcome message refreshed! {msg.jump_url}", ephemeral=True)
            except Exception as e:
                logging.error(f"Error refreshing welcome message: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Failed to refresh welcome message. Check logs for details.", ephemeral=True)
                    
        except Exception as e:
            logging.error(f"Error in refresh command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while processing the command.", ephemeral=True)
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}") 