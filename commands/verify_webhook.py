import discord
from discord.ext import commands
import json
import logging
import os
from datetime import datetime, timezone
from utils import safe_json_write, safe_json_read

USER_DATA_FILE = 'user_data.json'

@commands.command(name="verifywebhook")
async def verify_webhook(ctx, user_id: str = None):
    """
    Manually verify a user after receiving Typeform webhook data
    Usage: !verifywebhook <user_id>
    """
    if not user_id:
        await ctx.send("❌ Please provide a user ID. Usage: `!verifywebhook <user_id>`")
        return
    
    # Check if user exists in the server
    user = ctx.guild.get_member(int(user_id))
    if not user:
        await ctx.send(f"❌ User with ID {user_id} not found in this server.")
        return
    
    try:
        # Load user data
        user_data = safe_json_read(USER_DATA_FILE, {})
        
        if user_id not in user_data:
            await ctx.send(f"❌ User {user.mention} ({user_id}) not found in user data.")
            return
        
        user_info = user_data[user_id]
        
        # Check if already verified
        if user_info.get('lead_captured', False) and user_info.get('has_access', False):
            await ctx.send(f"✅ User {user.mention} is already verified.")
            return
        
        # Mark as lead captured (Typeform submitted)
        user_info['lead_captured'] = True
        user_info['webhook_verified_at'] = datetime.now(timezone.utc).isoformat()
        
        # Save updated data
        user_data[user_id] = user_info
        safe_json_write(USER_DATA_FILE, user_data)
        
        # Get member role
        member_role_id = int(os.getenv('MEMBER_ROLE_ID', 0))
        if member_role_id:
            member_role = ctx.guild.get_role(member_role_id)
            if member_role and member_role not in user.roles:
                await user.add_roles(member_role)
                logging.info(f"Added member role to user {user_id} via webhook verification")
        
        # Send confirmation to user
        embed = discord.Embed(
            title="✅ You've been verified!",
            description=(
                "Great news! We've received your survey submission and you're now verified.\n\n"
                "You now have full access to The VoCreations Mentorship community!\n\n"
                "Welcome aboard! 🎉"
            ),
            color=0x00ff00
        )
        
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            logging.warning(f"Could not send DM to user {user_id}")
        
        await ctx.send(f"✅ Successfully verified user {user.mention} ({user_id})")
        logging.info(f"User {user_id} verified via webhook command")
        
        # Also add a reaction to indicate successful verification
        try:
            await ctx.message.add_reaction("✅")
        except:
            pass
        
    except Exception as e:
        logging.error(f"Error in verify_webhook command: {e}")
        await ctx.send(f"❌ An error occurred while verifying user {user.mention}: {str(e)}")

async def setup(bot):
    bot.add_command(verify_webhook)

