import discord
from discord.ext import commands
import os
import logging
import json
from datetime import datetime, timezone

async def setup(bot):
    @bot.tree.command(name="viewleads", description="View captured lead information")
    @discord.app_commands.default_permissions(administrator=True)
    async def view_leads(interaction: discord.Interaction, user: discord.Member = None):
        """View captured lead information (admin only)"""
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
            
            # Load lead data
            try:
                with open('lead_data.json', 'r') as f:
                    lead_data = json.load(f)
            except FileNotFoundError:
                lead_data = {}
            
            if user:
                # Show specific user's lead data
                user_id = str(user.id)
                if user_id not in lead_data:
                    await interaction.response.send_message(
                        f"❌ No lead data found for {user.mention}", ephemeral=True
                    )
                    return
                
                lead_info = lead_data[user_id]
                
                embed = discord.Embed(
                    title=f"📋 Lead Information: {user.display_name}",
                    description=f"User ID: `{user.id}`",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                
                embed.add_field(name="Full Name", value=lead_info.get('name', 'N/A'), inline=True)
                embed.add_field(name="Email", value=lead_info.get('email', 'N/A'), inline=True)
                embed.add_field(name="Phone", value=lead_info.get('phone', 'Not provided'), inline=True)
                embed.add_field(name="Experience", value=lead_info.get('experience', 'N/A'), inline=True)
                embed.add_field(name="Goals", value=lead_info.get('goals', 'N/A')[:200] + "..." if len(lead_info.get('goals', '')) > 200 else lead_info.get('goals', 'N/A'), inline=False)
                
                if lead_info.get('submitted_at'):
                    submit_time = datetime.fromtimestamp(lead_info['submitted_at'], tz=timezone.utc)
                    embed.add_field(name="Submitted", value=submit_time.strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
                
                embed.set_thumbnail(url=user.display_avatar.url)
                embed.set_footer(text=f"Requested by {interaction.user.name}")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            else:
                # Show all leads
                if not lead_data:
                    await interaction.response.send_message(
                        "📋 No lead data found.", ephemeral=True
                    )
                    return
                
                embed = discord.Embed(
                    title="📋 All Captured Leads",
                    description=f"Total leads: {len(lead_data)}",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                
                # Show first 10 leads
                count = 0
                for user_id, lead_info in lead_data.items():
                    if count >= 10:
                        break
                    
                    try:
                        member = interaction.guild.get_member(int(user_id))
                        if member:
                            name = f"{member.display_name} ({lead_info.get('name', 'N/A')})"
                        else:
                            name = f"User {user_id} ({lead_info.get('name', 'N/A')})"
                    except:
                        name = f"User {user_id} ({lead_info.get('name', 'N/A')})"
                    
                    email = lead_info.get('email', 'N/A')
                    experience = lead_info.get('experience', 'N/A')
                    
                    embed.add_field(
                        name=f"{count + 1}. {name}",
                        value=f"Email: {email}\nExperience: {experience}",
                        inline=False
                    )
                    count += 1
                
                if len(lead_data) > 10:
                    embed.add_field(
                        name="Note",
                        value=f"Showing first 10 of {len(lead_data)} leads. Use `/viewleads @user` to see specific lead details.",
                        inline=False
                    )
                
                embed.set_footer(text=f"Requested by {interaction.user.name}")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            logging.error(f"Error viewing leads: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while viewing leads.", ephemeral=True)
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")
