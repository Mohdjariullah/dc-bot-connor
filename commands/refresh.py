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
        
        async def send_response(message, ephemeral=True):
            """Helper function to safely send response or followup"""
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(message, ephemeral=ephemeral)
                else:
                    await interaction.followup.send(message, ephemeral=ephemeral)
            except Exception as e:
                logging.error(f"Failed to send response: {e}")
        
        try:
            # SECURITY: Check authorization
            from main import is_authorized_guild_or_owner
            if not is_authorized_guild_or_owner(interaction):
                await send_response("❌ You are not authorized to use this command.")
                return
            
            # SECURITY: Block DMs and check admin permissions
            if not interaction.guild:
                await send_response("❌ This command can only be used in a server!")
                return
            
            if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
                await send_response("❌ You need Administrator permissions!")
                return
            
            # Get configuration from main.py
            from main import WELCOME_CHANNEL_ID, get_or_create_welcome_message
            
            # Get the welcome channel
            welcome_channel = interaction.guild.get_channel(WELCOME_CHANNEL_ID)
            if not welcome_channel:
                await send_response("❌ Welcome channel not found!")
                return
            
            # Create welcome embed using centralized config
            from config import get_welcome_embed
            embed = get_welcome_embed()
            
            # Use VerificationView
            msg = await get_or_create_welcome_message(welcome_channel, embed, VerificationView())
            await send_response(f"✅ Welcome message refreshed! {msg.jump_url}")
            
        except Exception as e:
            logging.error(f"Error in refresh command: {e}")
            await send_response("❌ Failed to refresh welcome message. Check logs for details.") 