import discord
from discord.ext import commands
import json
import logging
import os
import io
from config import CONVERSATION_CONTEXT_FILE

async def setup(bot):
    @bot.tree.command(name="clear_context", description="Clear all AI conversation context messages (Owner only)")
    async def clear_context(interaction: discord.Interaction):
        """Clear all AI conversation context messages - Owner only command"""
        try:
            # SECURITY: Check if user is bot owner
            from main import OWNER_USER_IDS
            if interaction.user.id not in OWNER_USER_IDS:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ This command is only available to bot owners.", ephemeral=True
                    )
                return
            
            # Check if the conversation context file exists
            if not os.path.exists(CONVERSATION_CONTEXT_FILE):
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "✅ Conversation context file doesn't exist (already empty).", ephemeral=True
                    )
                return
            
            # Read the current content before clearing
            try:
                with open(CONVERSATION_CONTEXT_FILE, 'r') as f:
                    context_data = f.read()
                
                # Send the file content to the owner via DM
                dm_sent = False
                try:
                    # Create a Discord file object from the content
                    file_content = discord.File(
                        io.BytesIO(context_data.encode('utf-8')), 
                        filename='ai_conversation_context_backup.json'
                    )
                    
                    # Send DM with the file
                    await interaction.user.send(
                        content="📄 **AI Conversation Context Backup**\nHere's the conversation context that was cleared:",
                        file=file_content
                    )
                    logging.info(f"Conversation context backup sent to owner {interaction.user.id} ({interaction.user.name})")
                    dm_sent = True
                    
                except discord.Forbidden:
                    logging.warning(f"Could not send DM to owner {interaction.user.id} - DMs may be disabled")
                    # Still proceed with clearing, but mention the DM issue
                
                # Clear the conversation context file by writing an empty object
                with open(CONVERSATION_CONTEXT_FILE, 'w') as f:
                    json.dump({}, f, indent=2)
                
                logging.info(f"Conversation context cleared by owner {interaction.user.id} ({interaction.user.name})")
                
                dm_status = " and backup sent to your DMs" if dm_sent else " (couldn't send DM backup - DMs may be disabled)"
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"✅ All AI conversation context messages have been cleared successfully!{dm_status}", ephemeral=True
                    )
                    
            except Exception as file_error:
                logging.error(f"Error clearing conversation context file: {file_error}")
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Failed to clear conversation context file. Check logs for details.", ephemeral=True
                    )
                    
        except Exception as e:
            logging.error(f"Error in clear_context command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while processing the command.", ephemeral=True
                    )
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")
