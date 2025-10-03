import discord
from discord.ext import commands
import logging

async def setup(bot):
    @bot.tree.command(name="ai_channel", description="Enable or disable AI chat in a channel")
    @discord.app_commands.describe(
        action="The action to perform: enable, disable, status, or list",
        channel="The channel to manage (defaults to current channel)"
    )
    @discord.app_commands.choices(action=[
        discord.app_commands.Choice(name="Enable AI Chat", value="enable"),
        discord.app_commands.Choice(name="Disable AI Chat", value="disable"),
        discord.app_commands.Choice(name="Check Status", value="status"),
        discord.app_commands.Choice(name="List Enabled Channels", value="list")
    ])
    async def ai_channel(interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Enable or disable AI chat in a channel"""
        try:
            # Get the AI channel cog
            ai_cog = bot.get_cog('AIChannel')
            if not ai_cog:
                await interaction.response.send_message("❌ AI channel system is not available.", ephemeral=True)
                return
            
            # Input validation
            is_valid, error_msg = ai_cog.validate_input(action)
            if not is_valid:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
                return
            
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
            
            # Use current channel if no channel specified
            if channel is None:
                channel = interaction.channel
            
            # Load current enabled channels (async)
            enabled_channels = await ai_cog.load_ai_channels()
            guild_id = str(interaction.guild.id)
            channel_id = str(channel.id)
            
            if action.lower() == "enable":
                # Enable AI in this channel
                if guild_id not in enabled_channels:
                    enabled_channels[guild_id] = []
                
                if channel_id not in enabled_channels[guild_id]:
                    enabled_channels[guild_id].append(channel_id)
                    await ai_cog.save_ai_channels(enabled_channels)
                    
                    embed = discord.Embed(
                        title="✅ AI Chat Enabled",
                        description=f"AI chat is now enabled in {channel.mention}",
                        color=discord.Color.green()
                    )
                    embed.add_field(
                        name="How it works",
                        value="The AI will now respond to every message in this channel. Use `/ai_channel disable` to turn it off.",
                        inline=False
                    )
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.response.send_message(
                        f"❌ AI chat is already enabled in {channel.mention}", 
                        ephemeral=True
                    )
            
            elif action.lower() == "disable":
                # Disable AI in this channel
                if guild_id in enabled_channels and channel_id in enabled_channels[guild_id]:
                    enabled_channels[guild_id].remove(channel_id)
                    await ai_cog.save_ai_channels(enabled_channels)
                    
                    embed = discord.Embed(
                        title="❌ AI Chat Disabled",
                        description=f"AI chat is now disabled in {channel.mention}",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.response.send_message(
                        f"❌ AI chat is not enabled in {channel.mention}", 
                        ephemeral=True
                    )
            
            elif action.lower() == "status":
                # Check status of AI in this channel
                is_enabled = guild_id in enabled_channels and channel_id in enabled_channels[guild_id]
                
                embed = discord.Embed(
                    title="📊 AI Chat Status",
                    description=f"Channel: {channel.mention}",
                    color=discord.Color.blue() if is_enabled else discord.Color.gray()
                )
                embed.add_field(
                    name="Status",
                    value="✅ Enabled" if is_enabled else "❌ Disabled",
                    inline=True
                )
                
                if guild_id in enabled_channels:
                    enabled_count = len(enabled_channels[guild_id])
                    embed.add_field(
                        name="Total Enabled Channels",
                        value=str(enabled_count),
                        inline=True
                    )
                
                await interaction.response.send_message(embed=embed)
            
            elif action.lower() == "list":
                # List all enabled channels
                if guild_id in enabled_channels and enabled_channels[guild_id]:
                    channel_mentions = []
                    for ch_id in enabled_channels[guild_id]:
                        ch = interaction.guild.get_channel(int(ch_id))
                        if ch:
                            channel_mentions.append(ch.mention)
                    
                    embed = discord.Embed(
                        title="📋 AI Enabled Channels",
                        description="\n".join(channel_mentions) if channel_mentions else "No channels enabled",
                        color=discord.Color.blue()
                    )
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.response.send_message(
                        "❌ No channels have AI chat enabled", 
                        ephemeral=True
                    )
            
            else:
                await interaction.response.send_message(
                    "❌ Invalid action! Use: `enable`, `disable`, `status`, or `list`", 
                    ephemeral=True
                )
                
        except Exception as e:
            logging.error(f"Error in ai_channel command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while processing the command.", ephemeral=True)
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")
