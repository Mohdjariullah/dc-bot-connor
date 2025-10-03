import discord
from discord.ext import commands
import os
import logging
import json

async def setup(bot):
    @bot.tree.command(name="addunverified", description="Add unverified role to a user")
    @discord.app_commands.default_permissions(administrator=True)
    async def add_unverified_role(interaction: discord.Interaction, user: discord.Member):
        """Add unverified role to a user (admin only)"""
        # SECURITY: Check authorization
        from main import is_authorized_guild_or_owner
        if not is_authorized_guild_or_owner(interaction):
            return await interaction.response.send_message(
                "❌ You are not authorized to use this command.", ephemeral=True
            )
        
        # SECURITY: Block DMs and check admin permissions
        if not interaction.guild:
            return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ You need Administrator permissions!", ephemeral=True)
        
        try:
            unverified_role_id = int(os.getenv('UNVERIFIED_ROLE_ID', 0))
            if not unverified_role_id:
                await interaction.response.send_message("❌ UNVERIFIED_ROLE_ID not configured!", ephemeral=True)
                return
            
            unverified_role = interaction.guild.get_role(unverified_role_id)
            if not unverified_role:
                await interaction.response.send_message("❌ Unverified role not found!", ephemeral=True)
                return
            
            if unverified_role in user.roles:
                await interaction.response.send_message(f"❌ {user.mention} already has the unverified role!", ephemeral=True)
                return
            
            await user.add_roles(unverified_role)
            
            # Update user data
            try:
                with open('user_data.json', 'r') as f:
                    user_data = json.load(f)
            except FileNotFoundError:
                user_data = {}
            
            user_id_str = str(user.id)
            if user_id_str in user_data:
                user_data[user_id_str]['unverified_role_assigned'] = True
            else:
                # Create new user data if they don't exist
                user_data[user_id_str] = {
                    'joined_at': 0,
                    'has_access': False,
                    'role_assigned': False,
                    'unverified_role_assigned': True,
                    'button_clicked_at': 0
                }
            
            with open('user_data.json', 'w') as f:
                json.dump(user_data, f, indent=2)
            
            embed = discord.Embed(
                title="🔒 Unverified Role Added",
                description=f"**{user.mention}** has been assigned the Unverified role",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
            embed.add_field(name="Role Added", value=f"🔒 Unverified", inline=True)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"Added by {interaction.user.name}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Log to logs channel
            logs_channel_id = int(os.getenv('LOGS_CHANNEL_ID', 0))
            if logs_channel_id:
                logs_channel = interaction.guild.get_channel(logs_channel_id)
                if logs_channel:
                    try:
                        await logs_channel.send(embed=embed)
                    except discord.Forbidden:
                        logging.warning(f"Bot doesn't have permission to send messages to logs channel {logs_channel_id}")
                    except Exception as e:
                        logging.error(f"Error sending log message: {e}")
                    
        except Exception as e:
            logging.error(f"Error adding unverified role: {e}")
            await interaction.response.send_message("❌ An error occurred while adding the role.", ephemeral=True) 