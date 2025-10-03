import discord
from discord.ext import commands
import os
import logging
import json

async def setup(bot):
    @bot.tree.command(name="removemember", description="Remove member role from a user")
    @discord.app_commands.default_permissions(administrator=True)
    async def remove_member_role(interaction: discord.Interaction, user: discord.Member):
        """Remove member role from a user (admin only)"""
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
            
            member_role_id = int(os.getenv('MEMBER_ROLE_ID', 0))
            if not member_role_id:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ MEMBER_ROLE_ID not configured!", ephemeral=True)
                return
            
            member_role = interaction.guild.get_role(member_role_id)
            if not member_role:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Member role not found!", ephemeral=True)
                return
            
            if member_role not in user.roles:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ {user.mention} doesn't have the member role!", ephemeral=True)
                return
            
            await user.remove_roles(member_role)
            
            # Update user data
            try:
                with open('user_data.json', 'r') as f:
                    user_data = json.load(f)
            except FileNotFoundError:
                user_data = {}
            
            user_id_str = str(user.id)
            if user_id_str in user_data:
                user_data[user_id_str]['has_access'] = False
                user_data[user_id_str]['role_assigned'] = False
                
                with open('user_data.json', 'w') as f:
                    json.dump(user_data, f, indent=2)
            
            embed = discord.Embed(
                title="🔓 Member Role Removed",
                description=f"**{user.mention}** has had their Member role removed",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
            embed.add_field(name="Role Removed", value=f"🔓 Member", inline=True)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"Removed by {interaction.user.name}")
            
            if not interaction.response.is_done():
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
            logging.error(f"Error removing member role: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while removing the role.", ephemeral=True)
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")

    @bot.tree.command(name="cleanup_roles", description="Remove unverified role from users who have member role")
    @discord.app_commands.default_permissions(administrator=True)
    async def cleanup_roles(interaction: discord.Interaction):
        """Remove unverified role from users who already have member role (admin only)"""
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
            
            member_role_id = int(os.getenv('MEMBER_ROLE_ID', 0))
            unverified_role_id = int(os.getenv('UNVERIFIED_ROLE_ID', 0))
            
            if not member_role_id or not unverified_role_id:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ MEMBER_ROLE_ID or UNVERIFIED_ROLE_ID not configured!", ephemeral=True)
                return
            
            member_role = interaction.guild.get_role(member_role_id)
            unverified_role = interaction.guild.get_role(unverified_role_id)
            
            if not member_role or not unverified_role:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Member or Unverified role not found!", ephemeral=True)
                return
            
            # Find users with both roles
            users_to_cleanup = []
            for member in interaction.guild.members:
                if member_role in member.roles and unverified_role in member.roles:
                    users_to_cleanup.append(member)
            
            if not users_to_cleanup:
                if not interaction.response.is_done():
                    await interaction.response.send_message("✅ No users found with both member and unverified roles!", ephemeral=True)
                return
            
            # Remove unverified role from these users
            cleaned_users = []
            for member in users_to_cleanup:
                try:
                    await member.remove_roles(unverified_role)
                    cleaned_users.append(member)
                    logging.info(f"Removed unverified role from {member.display_name} ({member.id}) - they have member role")
                except Exception as e:
                    logging.error(f"Error removing unverified role from {member.id}: {e}")
            
            # Update user data
            try:
                with open('user_data.json', 'r') as f:
                    user_data = json.load(f)
            except FileNotFoundError:
                user_data = {}
            
            for member in cleaned_users:
                user_id_str = str(member.id)
                if user_id_str in user_data:
                    user_data[user_id_str]['unverified_role_assigned'] = False
                    user_data[user_id_str]['has_access'] = True
                    user_data[user_id_str]['role_assigned'] = True
            
            if cleaned_users:
                with open('user_data.json', 'w') as f:
                    json.dump(user_data, f, indent=2)
            
            # Create response embed
            embed = discord.Embed(
                title="🧹 Role Cleanup Complete",
                description=f"Removed unverified role from **{len(cleaned_users)}** users who already have member role",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            if cleaned_users:
                user_list = "\n".join([f"• {user.mention} (`{user.id}`)" for user in cleaned_users[:10]])  # Show first 10
                if len(cleaned_users) > 10:
                    user_list += f"\n... and {len(cleaned_users) - 10} more"
                
                embed.add_field(name="Users Cleaned", value=user_list, inline=False)
            
            embed.set_footer(text=f"Cleaned by {interaction.user.name}")
            
            if not interaction.response.is_done():
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
            logging.error(f"Error in cleanup_roles: {e}")
            
            # Report critical error to owners
            try:
                from cogs.verification import report_critical_error
                bot = interaction.client if hasattr(interaction, 'client') else None
                await report_critical_error("Role Cleanup Error", f"Error in cleanup_roles command: {e}", bot, interaction)
            except Exception as report_error:
                logging.error(f"Failed to report critical error: {report_error}")
            
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred during role cleanup.", ephemeral=True)
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}") 