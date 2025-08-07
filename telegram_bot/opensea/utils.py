from telegram_bot.opensea.keyboards.config_keyboards import ConfigKeyboards


def build_blacklist_string(blacklist):
    """Helper function to format blacklist items for display."""
    return '\n\n' + '\n'.join([f"<code>{item}</code>" for item in sorted(blacklist)]) if blacklist else ""

async def edit_message_text(text, message, state, bot, custom_keyboard=None):
    """Helper function to edit a message with a specific text."""
    
    data = await state.get_data()
    message_id = data.get('message_id')

    await bot.edit_message_text(

        chat_id=message.from_user.id,
        message_id=message_id,
        text=text,
        parse_mode='HTML',
        reply_markup=custom_keyboard or ConfigKeyboards.opensea_config_keyboard()

    )