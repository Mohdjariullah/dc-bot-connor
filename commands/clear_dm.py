import discord
from discord.ext import commands
import logging
import asyncio

async def setup(bot):
    @bot.tree.command(name="clear_dm", description="Delete the bot's DM messages with a user (admin only)")
    @discord.app_commands.describe(user="User whose DM with the bot should be cleared", limit="Max messages to scan (default 200)")
    @discord.app_commands.default_permissions(administrator=True)
    async def clear_dm(interaction: discord.Interaction, user: discord.User, limit: int = 200):
        """Delete the bot's own messages in its DM with a specific user"""
        try:
            # SECURITY: Check authorization and guild context (admin-only, allow from guild only)
            from main import is_authorized_guild_or_owner
            if not is_authorized_guild_or_owner(interaction):
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
                return

            if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ You need Administrator permissions!", ephemeral=True)
                return

            # Cap limit to a safe maximum
            if limit <= 0:
                limit = 50
            limit = min(limit, 1000)

            # Get or create DM channel with the target user
            dm = user.dm_channel or await user.create_dm()
            if dm is None:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Unable to open DM channel with that user.", ephemeral=True)
                return

            bot_user = interaction.client.user
            deleted_count = 0
            scanned = 0

            # Inform start
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"🧹 Starting DM cleanup with {user.mention} (scanning up to {limit} messages)...",
                    ephemeral=True
                )

            # Delete only messages authored by the bot
            async for message in dm.history(limit=limit):
                scanned += 1
                if message.author.id == bot_user.id:
                    try:
                        await message.delete()
                        deleted_count += 1
                        # Gentle pacing to avoid hitting rate limits on large deletions
                        await asyncio.sleep(0.2)
                    except discord.Forbidden:
                        logging.warning("Forbidden deleting a DM message; stopping.")
                        break
                    except discord.HTTPException as e:
                        logging.error(f"HTTPException while deleting DM message: {e}")
                        # Continue, but slow slightly
                        await asyncio.sleep(0.5)

            # Follow-up summary
            try:
                await interaction.followup.send(
                    f"✅ Done. Scanned {scanned} messages, deleted {deleted_count} bot messages in DMs with {user.mention}.",
                    ephemeral=True
                )
            except Exception:
                pass

        except Exception as e:
            logging.error(f"Error in clear_dm command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while clearing DMs.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while clearing DMs.", ephemeral=True)
            except Exception:
                pass


