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
# Настройки эффекта
BLUR_SIGMA = 20      # Сила ореола свечения (15-30)
BLOOM_OPACITY = 0.65 # Насколько сильно рассеивается свет от жира (0.3 - слабенько, 0.8 - конкретно заляпана)

ffmpeg_cmd = [
    'ffmpeg', '-y',
    '-i', input_path,
    '-filter_complex', (
        # 1. Приводим к 512x512 и дублируем поток на 2 слоя ([main] и [blur])
        '[0:v]scale=512:512:force_original_aspect_ratio=increase,crop=512:512,split=2[main][blur],'
        
        # 2. Размываем второй слой и задираем ему яркость (это наши жирные блики)
        f'[blur]gblur=sigma={BLUR_SIGMA},eq=contrast=1.3:brightness=0.08[glow];'
        
        # 3. Смешиваем основной кадр и свечение в режиме "screen",
        # затем роняем контраст (eq) и добавляем затемнение по краям (vignette)
        f'[main][glow]blend=all_mode=screen:opacity={BLOOM_OPACITY},'
        'eq=contrast=0.72:brightness=0.08:saturation=0.85,'
        'vignette=angle=0.45'
    ),
    '-c:v', 'libx264',
    '-preset', 'ultrafast',
    '-crf', '26',
    '-c:a', 'aac',
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
