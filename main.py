from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Токен вашего бота
TOKEN = "7384843477:AAFsitozSLRZvyFAuu_ZSEVSm1st_cnC0DA"

# Создание объекта Application
app = Application.builder().token(TOKEN).build()

# Функция обработки текстовых сообщений
async def handle_text(update: Update, context: CallbackContext) -> None:
    # Отправка сообщения в указанный канал
    await context.bot.send_message(chat_id='@SportPrognoze2', text=update.message.text)

# Создание обработчика сообщений
text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)

# Добавление обработчика в приложение
app.add_handler(text_handler)

# Запуск бота
if __name__ == "__main__":
    app.run_polling()
