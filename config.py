"""
Centralized configuration for all Discord bot components
"""
import os
import discord

# Environment Variables
GUILD_ID = int(os.getenv('GUILD_ID', 0))
WELCOME_CHANNEL_ID = int(os.getenv('WELCOME_CHANNEL_ID', 0))
LOGS_CHANNEL_ID = int(os.getenv('LOGS_CHANNEL_ID', 0))
SUBMISSION_LOGS_CHANNEL_ID = int(os.getenv('SUBMISSION_LOGS_CHANNEL_ID', 0))


# Role IDs
PREMIUM_ROLE_ID = int(os.getenv('PREMIUM_ROLE_ID', 0))
VIP_ROLE_ID = int(os.getenv('VIP_ROLE_ID', 0))
HUNDRED_K_ROLE_ID = int(os.getenv('HUNDRED_K_ROLE_ID', 0))
MEMBER_ROLE_ID = int(os.getenv('MEMBER_ROLE_ID', 0))
UNVERIFIED_ROLE_ID = int(os.getenv('UNVERIFIED_ROLE_ID', 0))

# External Links
CALENDLY_LINK = os.getenv('CALENDLY_LINK', 'https://calendly.com/aidaptics/30min')
TYPEFORM_LINK = os.getenv('TYPEFORM_LINK', 'https://form.typeform.com/to/VkuOahlj')

# Images
PB_TRADING_THUMBNAIL = "https://cdn.discordapp.com/attachments/1370112450397081733/1424999474068979762/4ce7853c95d5c3aa5e7a8784110c714a.png?ex=68e5fdad&is=68e4ac2d&hm=f9f90073e5b43a48a6b2c453e7e773c9fef8d58b041be34876827470d5414b77"

# Timing Configuration
ROLE_ASSIGNMENT_DELAY = int(os.getenv('ROLE_ASSIGNMENT_DELAY', 10))
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 30))

# AI Configuration
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'deepseek/deepseek-r1-0528-qwen3-8b:free')

# File Paths
USER_DATA_FILE = 'user_data.json'
COOLDOWN_FILE = 'button_cooldowns.json'
LEAD_DATA_FILE = 'lead_data.json'
WELCOME_MESSAGE_FILE = 'welcome_message.json'
AI_CHANNELS_FILE = 'ai_enabled_channels.json'
CONVERSATION_CONTEXT_FILE = 'ai_conversation_context.json'
SCHEDULE_FILE = 'daily_channel_schedules.json'
LOGGED_MEMBERS_FILE = 'logged_members.json'

# Rate Limiting
RATE_LIMIT_SECONDS = 10
RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_COOLDOWN = 30

# Premium Role Mapping
def get_premium_role_ids():
    """Get premium role IDs that should be monitored"""
    premium_roles = {}
    if VIP_ROLE_ID:
        premium_roles[VIP_ROLE_ID] = None  # Will be filled with actual role name
    if HUNDRED_K_ROLE_ID:
        premium_roles[HUNDRED_K_ROLE_ID] = None  # Will be filled with actual role name
    return premium_roles

# Welcome Messages
def get_welcome_embed():
    """Get the standard welcome embed"""
    embed = discord.Embed(
        title="🎉 Welcome to The Apex Ecom Mentorship! 🎉",
        description=(
            "You've joined a 1:1 program designed to help dropshippers scale past $100K/month. This mentorship is about precision, clarity, and execution — all personalized to you with direct coaching from Sebastian.\n\n"
            "Before you can access the Discord and get started, we need to understand your business and where you're at right now.\n\n"
            "👉 **Complete the Onboarding Survey to unlock access.**\n\n"
            "No survey = no Discord access. Take 5 minutes now and let's get you moving forward."
        ),
        color=0xFFFFFF
    )
    embed.set_footer(text="Complete Your Onboarding Survey Today!")
    embed.set_thumbnail(url=PB_TRADING_THUMBNAIL)
    return embed

def get_verification_dm_embed():
    """Get the verification DM embed"""
    embed = discord.Embed(
        title="👋 Welcome to The Apex Ecom Mentorship!",
        description=(
            "You've joined a 1:1 program designed to help dropshippers scale past $100K/month. This mentorship is about precision, clarity, and execution — all personalized to you with direct coaching from Sebastian.\n\n"
            "Before you can access the Discord and get started, we need to understand your business and where you're at right now.\n\n"
            "👉 **Complete the Onboarding Survey to unlock access.**\n\n"
            "No survey = no Discord access. Take 5 minutes now and let's get you moving forward."
        ),
        color=0x00ff00
    )
    embed.set_thumbnail(url=PB_TRADING_THUMBNAIL)
    return embed

def get_survey_embed(premium_role_name, user_id):
    """Get the survey completion embed"""
    embed = discord.Embed(
        title="📋 Complete Your Onboarding Survey to Unlock Access",
        description=(
            f"Welcome to The Apex Ecom Mentorship! We've detected your **{premium_role_name}** tier.\n\n"
            "Complete this quick onboarding survey to unlock access to the Discord and get started with your personalized 1:1 mentorship!\n\n"
            "👉 **Click the link below to complete the survey**\n\n"
            "**What happens next?**\n"
            "1. Complete the onboarding survey using the link below\n"
            "2. We'll automatically restore your premium role\n"
            "3. You'll have full access to The Apex Ecom Mentorship Discord!"
        ),
        color=0x00ff00
    )
    
    # Add Typeform link with user ID parameter
    typeform_link = f"{TYPEFORM_LINK}#auth_code={user_id}"
    embed.add_field(
        name="🔗 Complete Survey",
        value=f"[Click here to fill out the survey]({typeform_link})",
        inline=False
    )
    
    # Add user ID info for debugging
    embed.add_field(
        name="📋 Your User ID",
        value=f"`{user_id}` (keep this for reference)",
        inline=False
    )
    
    embed.set_footer(text="We'll automatically verify you once you submit the survey!")
    return embed

def get_verification_complete_embed(premium_role_name):
    """Get the verification complete embed"""
    embed = discord.Embed(
        title="✅ Survey Complete!",
        description=(
            f"Survey complete! You've been restored to your **{premium_role_name}** role.\n\n"
            "Now it's time to schedule your onboarding call.\n\n"
            "**This call is where Sebastian will:**\n"
            "• Review your current operation in detail\n"
            "• Build your personalized scaling roadmap\n"
            "• Plug you directly into the mentorship so you can start executing immediately\n\n"
            "👉 **Book your onboarding call now to unlock full access to The Apex Ecom Mentorship Discord.**\n\n"
            "Welcome to The Apex Ecom Mentorship! 🎉"
        ),
        color=0x00ff00
    )
    embed.add_field(
        name="📞 Schedule Your Onboarding Call",
        value=f"[Click here to book your call]({CALENDLY_LINK})",
        inline=False
    )
    return embed
