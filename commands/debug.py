import discord
from discord.ext import commands
import os
import json
from datetime import datetime, timezone
import logging

async def setup(bot):
    @bot.tree.command(name="debug", description="Debug information for admins")
    async def debug(interaction: discord.Interaction):
        """Debug command to check bot status"""
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
                title="🔧 Debug Information",
                description="Bot status and configuration details",
                color=discord.Color.blue()
            )
            
            # Check cogs status
            cogs_status = []
            expected_cogs = ['Verification', 'Welcome', 'AiChannel', 'WebhookHandler', 'RoleMonitor', 'UserLogger']
            for cog_name in expected_cogs:
                cog = bot.get_cog(cog_name)
                status = "✅ Loaded" if cog else "❌ Not loaded"
                cogs_status.append(f"{cog_name}: {status}")
            
            embed.add_field(name="📦 Cogs Status", value="\n".join(cogs_status), inline=False)
            
            # Check slash commands
            commands = [cmd.name for cmd in bot.tree.get_commands()]
            embed.add_field(
                name="⚡ Slash Commands", 
                value=f"{len(commands)} commands loaded\n`{', '.join(commands[:10])}{'...' if len(commands) > 10 else ''}`", 
                inline=False
            )
            
            # Check environment variables
            env_vars = []
            required_vars = [
                'GUILD_ID', 'WELCOME_CHANNEL_ID', 'LOGS_CHANNEL_ID', 
                'SUBMISSION_LOGS_CHANNEL_ID', 'USER_LOG_ID',
                'PREMIUM_ROLE_ID', 'VIP_ROLE_ID', 'HUNDRED_K_ROLE_ID', 
                'MEMBER_ROLE_ID', 'UNVERIFIED_ROLE_ID',
                'OPENROUTER_API_KEY', 'OPENROUTER_MODEL'
            ]
            for var in required_vars:
                value = os.getenv(var)
                if value:
                    # Mask sensitive values
                    if 'API_KEY' in var or 'SECRET' in var:
                        status = f"✅ Set (***{value[-4:]})"
                    else:
                        status = f"✅ Set ({value})"
                else:
                    status = "❌ Missing"
                env_vars.append(f"{var}: {status}")
            
            embed.add_field(name="🔧 Environment Variables", value="\n".join(env_vars), inline=False)
            
            # Check data files
            data_files = []
            file_paths = [
                'data/user_data.json', 'data/button_cooldowns.json', 'data/welcome_message.json',
                'data/ai_enabled_channels.json', 'data/ai_conversation_context.json', 'data/logged_members.json'
            ]
            for file_path in file_paths:
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            count = len(data)
                        elif isinstance(data, list):
                            count = len(data)
                        else:
                            count = "Unknown"
                    data_files.append(f"{file_path}: ✅ ({count} entries)")
                except FileNotFoundError:
                    data_files.append(f"{file_path}: ❌ Not found")
                except json.JSONDecodeError:
                    data_files.append(f"{file_path}: ⚠️ Invalid JSON")
                except Exception as e:
                    data_files.append(f"{file_path}: ❌ Error ({str(e)[:20]})")
            
            embed.add_field(name="📁 Data Files", value="\n".join(data_files), inline=False)
            
            # Bot stats
            uptime = datetime.now(timezone.utc) - bot.startup_time
            uptime_str = str(uptime).split('.')[0]  # Remove microseconds
            
            embed.add_field(
                name="📊 Bot Stats",
                value=f"**Uptime:** {uptime_str}\n**Latency:** {round(bot.latency * 1000)}ms\n**Guilds:** {len(bot.guilds)}\n**Users:** {len(bot.users)}", 
                inline=False
            )
            
            # Check guild-specific info
            if interaction.guild:
                guild_info = []
                guild_info.append(f"**Guild:** {interaction.guild.name}")
                guild_info.append(f"**Members:** {interaction.guild.member_count}")
                guild_info.append(f"**Channels:** {len(interaction.guild.channels)}")
                guild_info.append(f"**Roles:** {len(interaction.guild.roles)}")
                
                embed.add_field(name="🏰 Guild Info", value="\n".join(guild_info), inline=False)
            
            embed.set_footer(text=f"Debug info generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            logging.error(f"Error in debug command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while processing the command.", ephemeral=True)
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")
