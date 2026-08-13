import os
import subprocess
import telebot
from flask import Flask, request

TOKEN = os.getenv('BOT_TOKEN')
# Render сам выдает внешнюю ссылку в переменной RENDER_EXTERNAL_URL
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL') 

WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/' + TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '!', 200

@app.route('/')
def webhook_setup():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    return f"Webhook установлен на {WEBHOOK_URL}", 200

@bot.message_handler(content_types=['video_note', 'video'])
def handle_video(message):
    chat_id = message.chat.id
    
    file_id = message.video_note.file_id if message.video_note else message.video.file_id
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    input_path = f"/tmp/input_{chat_id}.mp4"
    output_path = f"/tmp/output_{chat_id}.mp4"

    with open(input_path, 'wb') as f:
        f.write(downloaded_file)

    # Обработка через FFmpeg
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-vf', 'scale=180:180:force_original_aspect_ratio=increase,crop=180:180,fps=12',
        '-c:v', 'libx264',
        '-b:v', '35k',
        '-preset', 'ultrafast',
        '-c:a', 'aac',
        '-b:a', '12k',
        '-ar', '8000',
        '-af', 'volume=6dB',
        output_path
    ]
    
    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with open(output_path, 'rb') as video_note:
        bot.send_video_note(chat_id, video_note)

    if os.path.exists(input_path): os.remove(input_path)
    if os.path.exists(output_path): os.remove(output_path)

if __name__ == '__main__':
    # Render передает порт в переменную PORT
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
