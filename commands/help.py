import discord
from discord.ext import commands

async def setup(bot):
    @bot.tree.command(name="help_admin", description="List all admin commands and their descriptions")
    async def help_admin(interaction: discord.Interaction):
        """List all admin commands and their descriptions"""
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
            
            embed = discord.Embed(
                title="🔧 Admin Commands",
                description="Available admin commands for the UGC Mastery bot",
                color=0x00ff00
            )
            
            embed.add_field(
                name="/setup",
                value="Set up the initial welcome message in the welcome channel",
                inline=False
            )
            
            embed.add_field(
                name="/refresh",
                value="Refresh the welcome message in the welcome channel",
                inline=False
            )
            
            embed.add_field(
                name="/checkuser",
                value="Check a user's status, roles, and data (includes cooldown info)",
                inline=False
            )
            
            embed.add_field(
                name="/fixuser",
                value="Fix user roles and status, automatically clears expired cooldowns",
                inline=False
            )
            
            embed.add_field(
                name="/addunverified",
                value="Add unverified role to a user manually",
                inline=False
            )
            
            embed.add_field(
                name="/removemember",
                value="Remove member role from a user",
                inline=False
            )
            
            embed.add_field(
                name="/cleanup_roles",
                value="Remove unverified role from users who already have member role",
                inline=False
            )
            
            embed.add_field(
                name="/daily_access_channel",
                value="Set up daily chat access for a channel (users can always see, chat on schedule)",
                inline=False
            )
            
            embed.add_field(
                name="/remove_daily_channel",
                value="Remove daily access schedule from a channel",
                inline=False
            )
            
            embed.add_field(
                name="/list_daily_channels",
                value="List all channels with daily access schedules",
                inline=False
            )
            
            embed.add_field(
                name="/test_daily_channel",
                value="Test the current status of a channel's daily access",
                inline=False
            )
            
            embed.add_field(
                name="/viewleads",
                value="View captured lead information (all leads or specific user)",
                inline=False
            )
            
            embed.add_field(
                name="/ai_channel",
                value="Enable/disable AI chat in channels (AI responds to all messages)",
                inline=False
            )
            
            embed.add_field(
                name="!verifywebhook <user_id>",
                value="Manually verify a user after receiving Typeform webhook data",
                inline=False
            )
            
            embed.add_field(
                name="/setup_welcome_verify",
                value="Set up the welcome-verify channel with verification button for premium users",
                inline=False
            )
            
            embed.add_field(
                name="Automatic Verification",
                value="The bot now automatically verifies users when Typeform webhook messages contain auth_code parameters. No manual intervention needed!",
                inline=False
            )
            
            embed.add_field(
                name="/help_admin",
                value="Show this help message with all admin commands",
                inline=False
            )
            
            embed.set_footer(text="All commands require Administrator permissions and must be used in the authorized server")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            import logging
            logging.error(f"Error in help_admin command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while processing the command.", ephemeral=True)
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}") 