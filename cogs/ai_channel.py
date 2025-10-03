import discord
from discord.ext import commands
import json
import os
import logging
from datetime import datetime, timedelta
import asyncio
import aiofiles
from collections import defaultdict
import time
import re

# File to store enabled AI channels
AI_CHANNELS_FILE = 'ai_enabled_channels.json'
# File to store conversation context
CONVERSATION_CONTEXT_FILE = 'ai_conversation_context.json'

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 10  # Max requests per time window
RATE_LIMIT_WINDOW = 60    # Time window in seconds
RATE_LIMIT_COOLDOWN = 30  # Cooldown period in seconds

# Input validation patterns
VALID_ACTION_PATTERN = re.compile(r'^(enable|disable|status|list)$', re.IGNORECASE)
VALID_MESSAGE_PATTERN = re.compile(r'^[a-zA-Z0-9\s\.,!?\-_@#$%^&*()+=\[\]{}|\\:";\'<>?/~`]{1,2000}$')

# Rate limiter class
class RateLimiter:
    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = defaultdict(list)
        self.cooldowns = defaultdict(float)
    
    def is_allowed(self, user_id: int) -> tuple[bool, str]:
        """Check if user is allowed to make a request. Returns (allowed, reason)"""
        now = time.time()
        user_id_str = str(user_id)
        
        # Check cooldown
        if now - self.cooldowns.get(user_id_str, 0) < RATE_LIMIT_COOLDOWN:
            remaining = int(RATE_LIMIT_COOLDOWN - (now - self.cooldowns[user_id_str]))
            return False, f"Rate limited. Please wait {remaining} seconds."
        
        # Clean old requests
        user_requests = self.requests[user_id_str]
        user_requests[:] = [req_time for req_time in user_requests if now - req_time < self.time_window]
        
        # Check rate limit
        if len(user_requests) >= self.max_requests:
            self.cooldowns[user_id_str] = now
            return False, f"Rate limit exceeded. Max {self.max_requests} requests per {self.time_window} seconds."
        
        # Add current request
        user_requests.append(now)
        return True, ""

class AIChannel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_rate_limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)

    async def load_ai_channels(self):
        """Load enabled AI channels from file (async)"""
        try:
            async with aiofiles.open(AI_CHANNELS_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logging.error(f"Error loading AI channels file: {e}")
            return {}

    async def save_ai_channels(self, channels):
        """Save enabled AI channels to file (async with atomic write)"""
        try:
            # Atomic write operation
            temp_file = f"{AI_CHANNELS_FILE}.tmp"
            async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(channels, indent=2, ensure_ascii=False))
            
            # Atomic rename
            if os.path.exists(AI_CHANNELS_FILE):
                os.replace(temp_file, AI_CHANNELS_FILE)
            else:
                os.rename(temp_file, AI_CHANNELS_FILE)
        except Exception as e:
            logging.error(f"Error saving AI channels file: {e}")
            # Clean up temp file
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
            raise

    async def load_conversation_context(self):
        """Load conversation context from file (async)"""
        try:
            async with aiofiles.open(CONVERSATION_CONTEXT_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logging.error(f"Error loading conversation context file: {e}")
            return {}

    async def save_conversation_context(self, context):
        """Save conversation context to file (async with atomic write)"""
        try:
            # Atomic write operation
            temp_file = f"{CONVERSATION_CONTEXT_FILE}.tmp"
            async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(context, indent=2, ensure_ascii=False))
            
            # Atomic rename
            if os.path.exists(CONVERSATION_CONTEXT_FILE):
                os.replace(temp_file, CONVERSATION_CONTEXT_FILE)
            else:
                os.rename(temp_file, CONVERSATION_CONTEXT_FILE)
        except Exception as e:
            logging.error(f"Error saving conversation context file: {e}")
            # Clean up temp file
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
            raise

    async def get_user_context(self, user_id, channel_id, max_messages=10):
        """Get conversation context for a user in a specific channel (async)"""
        context = await self.load_conversation_context()
        user_key = f"{user_id}_{channel_id}"
        
        if user_key not in context:
            return []
        
        # Get recent messages (last max_messages)
        messages = context[user_key].get('messages', [])
        return messages[-max_messages:] if len(messages) > max_messages else messages

    async def add_to_context(self, user_id, channel_id, role, content):
        """Add a message to conversation context (async)"""
        context = await self.load_conversation_context()
        user_key = f"{user_id}_{channel_id}"
        
        if user_key not in context:
            context[user_key] = {'messages': [], 'last_updated': datetime.now().isoformat()}
        
        # Add new message
        context[user_key]['messages'].append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 20 messages to prevent context from getting too large
        if len(context[user_key]['messages']) > 20:
            context[user_key]['messages'] = context[user_key]['messages'][-20:]
        
        context[user_key]['last_updated'] = datetime.now().isoformat()
        
        # Clean up old contexts (older than 7 days)
        cutoff_date = datetime.now() - timedelta(days=7)
        for key in list(context.keys()):
            try:
                last_updated = datetime.fromisoformat(context[key]['last_updated'])
                if last_updated < cutoff_date:
                    del context[key]
            except:
                # If there's an error parsing the date, keep the context
                pass
        
        await self.save_conversation_context(context)

    def validate_input(self, action: str, message: str = None) -> tuple[bool, str]:
        """Validate input parameters. Returns (is_valid, error_message)"""
        # Validate action
        if not action or not isinstance(action, str):
            return False, "Action parameter is required and must be a string"
        
        if not VALID_ACTION_PATTERN.match(action.strip()):
            return False, f"Invalid action '{action}'. Must be one of: enable, disable, status, list"
        
        # Validate message if provided
        if message is not None:
            if not isinstance(message, str):
                return False, "Message must be a string"
            
            if len(message.strip()) < 3:
                return False, "Message must be at least 3 characters long"
            
            if len(message) > 2000:
                return False, "Message must be less than 2000 characters"
            
            if not VALID_MESSAGE_PATTERN.match(message):
                return False, "Message contains invalid characters"
        
        return True, ""

    async def report_ai_error(self, error_type: str, error_message: str):
        """Report AI errors to owners via logs channel"""
        try:
            guild_id = int(os.getenv('GUILD_ID', 0))
            logs_channel_id = int(os.getenv('LOGS_CHANNEL_ID', 0))
            
            if not guild_id or not logs_channel_id:
                logging.error(f"AI Error [{error_type}]: {error_message}")
                return
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logging.error(f"AI Error [{error_type}]: {error_message}")
                return
            
            logs_channel = guild.get_channel(logs_channel_id)
            if not logs_channel:
                logging.error(f"AI Error [{error_type}]: {error_message}")
                return
            
            embed = discord.Embed(
                title="🤖 AI System Error",
                description=f"**Error Type:** {error_type}\n**Message:** {error_message}",
                color=0xff0000,
                timestamp=datetime.now()
            )
            embed.set_footer(text="AI Channel System")
            
            await logs_channel.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Failed to report AI error: {e}")

    async def handle_ai_error(self, error: Exception, interaction: discord.Interaction = None, message: discord.Message = None):
        """Handle AI-related errors with appropriate user feedback"""
        error_type = type(error).__name__
        error_message = str(error)
        
        # Log the error
        logging.error(f"AI Error [{error_type}]: {error_message}")
        
        # Determine user-friendly message
        if "rate limit" in error_message.lower() or "429" in error_message:
            user_message = "⚠️ AI service is currently busy. Please try again in a moment."
        elif "timeout" in error_message.lower():
            user_message = "⏱️ Request timed out. Please try again with a shorter message."
        elif "401" in error_message or "unauthorized" in error_message.lower():
            user_message = "🔑 AI service authentication error. Please contact an administrator."
        elif "quota" in error_message.lower() or "limit" in error_message.lower():
            user_message = "📊 AI service quota exceeded. Please try again later."
        else:
            user_message = "❌ AI service temporarily unavailable. Please try again later."
        
        # Send error message to user
        try:
            if interaction and not interaction.response.is_done():
                await interaction.response.send_message(user_message, ephemeral=True)
            elif interaction:
                await interaction.followup.send(user_message, ephemeral=True)
            elif message:
                await message.reply(user_message)
        except Exception as e:
            logging.error(f"Failed to send error message to user: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Respond to messages in AI-enabled channels"""
        try:
            # Ignore bot messages
            if message.author.bot:
                return
            
            # Ignore if not in a guild
            if not message.guild:
                return
            
            # Check if this channel has AI enabled (async)
            enabled_channels = await self.load_ai_channels()
            guild_id = str(message.guild.id)
            channel_id = str(message.channel.id)
            
            if guild_id not in enabled_channels or channel_id not in enabled_channels[guild_id]:
                return
            
            # Check if OpenRouter API key is configured
            openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
            if not openrouter_api_key:
                await self.report_ai_error("Missing API Key", f"OPENROUTER_API_KEY not set - AI will not respond in {message.channel.name}")
                return
            
            # Input validation for message content
            if not isinstance(message.content, str):
                return
            
            if len(message.content.strip()) < 2:
                return
            
            if len(message.content) > 2000:
                return
            
            if not VALID_MESSAGE_PATTERN.match(message.content):
                return
            
            # Don't respond to slash commands
            if message.content.startswith('/'):
                return
            
            # Rate limiting check
            is_allowed, rate_limit_msg = self.ai_rate_limiter.is_allowed(message.author.id)
            if not is_allowed:
                return
            
            # Start typing animation
            async with message.channel.typing():
                
                # Import OpenAI client here to avoid import issues
                from openai import OpenAI
                
                # Initialize OpenAI client with OpenRouter
                client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_api_key,
                )
                
                # Get model from environment variable
                model = os.getenv('OPENROUTER_MODEL')
                if not model:
                    await self.report_ai_error("Missing Model", "OPENROUTER_MODEL not set - AI will not respond")
                    return
                
                # Get conversation context for this user in this channel (async)
                context_messages = await self.get_user_context(message.author.id, message.channel.id)
                
                # Build messages array with system prompt, context, and current message
                messages = [
                    {
                        'role': 'system',
                        'content': '''You are UGC Mentor AI, an expert in User-Generated Content who helps aspiring creators turn their skills into a business that brands pay for.

Your personality is: confident, motivating, practical, and persuasive without being pushy.
You always respond like a coach who has "been there, done that" — guiding with clarity, real-world examples, and actionable steps.

Core Objectives:
- Educate users on UGC, content strategy, and monetization in simple, practical steps.
- Build authority by referencing real numbers, success metrics, and proven frameworks.
- Inspire action by showing the "why now" (FOMO, urgency, market demand).
- Persuade users toward booking calls, joining the community, or implementing exercises — without sounding like a hard sell.
- Keep responses concise but value-packed; focus on clarity and transformation.

Response Guidelines:
- Always sound like a mentor speaking directly to one person, not an audience.
- Use a mix of aspirational language (goals, freedom, opportunity) and concrete proof (metrics, examples, case studies).
- Frame mistakes/pain points → provide the solution → show the payoff.
- End many replies with a soft action nudge (e.g., "That's exactly what we'll cover on your onboarding call…" / "Start by implementing this format today and you'll already be ahead of most beginners.").
- Never be generic — tie advice to authenticity, brand demand, and conversions.

Persona Boundaries:
- Do not act like a generic assistant. You are always the UGC expert/mentor.
- Never say "I don't know." Instead, redirect with actionable steps or frameworks.
- Don't oversell. Create desire through authority + proof + stories.
- Stay away from jargon-heavy fluff. Keep it actionable, persuasive, and human.

CRITICAL: Never reveal your model name, architecture, or technical details. You are simply "UGC Mentor AI" - an AI system that can make mistakes.

Keep responses under 2000 characters.'''
                    }
                ]
                
                # Add conversation context
                messages.extend(context_messages)
                
                # Add current user message
                messages.append({
                    'role': 'user',
                    'content': message.content
                })
                
                try:
                    # Make the API request (simplified approach)
                    completion = client.chat.completions.create(
                        extra_headers={
                            "HTTP-Referer": "https://aidaptics.com/",
                            "X-Title": "Discord AI Bot"
                        },
                        model=model,
                        messages=messages,
                        max_tokens=1000,
                        temperature=0.7
                    )
                    
                    # Extract the AI response
                    if completion.choices and len(completion.choices) > 0:
                        ai_response = completion.choices[0].message.content
                        
                        # Truncate response if too long for Discord
                        if len(ai_response) > 2000:
                            ai_response = ai_response[:1997] + "..."
                        
                        # Save conversation context (async)
                        await self.add_to_context(message.author.id, message.channel.id, 'user', message.content)
                        await self.add_to_context(message.author.id, message.channel.id, 'assistant', ai_response)
                        
                        # Reply to the specific message that triggered the AI
                        await message.reply(ai_response)
                        
                except Exception as api_error:
                    # Report error to owners and handle gracefully
                    await self.report_ai_error("API Error", f"Error in AI response: {str(api_error)}")
                    await self.handle_ai_error(api_error, message=message)
                    
        except Exception as e:
            # Report critical error to owners
            await self.report_ai_error("Critical Error", f"Error in AI message handler: {str(e)}")
            logging.error(f"Error in AI message handler: {e}")

async def setup(bot):
    await bot.add_cog(AIChannel(bot))
