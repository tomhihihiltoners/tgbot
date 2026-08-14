import os
import subprocess
import telebot
from flask import Flask, request

TOKEN = os.getenv('BOT_TOKEN')
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL')

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
    if RENDER_URL and TOKEN:
        webhook_url = f"{RENDER_URL}/{TOKEN}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        return f"Webhook успешно установлен на {webhook_url}", 200
    return "Сервер работает!", 200


@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.reply_to(
        message,
        "Отправь мне кружок или видео, и я сделаю эффект заляпанной камеры!"
    )


@bot.message_handler(content_types=['video_note', 'video'])
def handle_video(message):
    chat_id = message.chat.id
    status_msg = bot.send_message(
        chat_id,
        "Обрабатываю видео... ⏳"
    )

    input_path = f"/tmp/input_{chat_id}_{message.message_id}.mp4"
    output_path = f"/tmp/output_{chat_id}_{message.message_id}.mp4"

    try:
        # 1. Скачиваем видео
        file_id = (
            message.video_note.file_id
            if message.video_note
            else message.video.file_id
        )

        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open(input_path, 'wb') as f:
            f.write(downloaded_file)

        # 2. ВИДЕО-ФИЛЬТР
        # scale -> приводим к квадрату 512x512
        # boxblur -> размытие
        # eq -> белёсая/грязная картинка
        # vignette -> затемнение по краям

        vf_chain = (
            "scale=512:512:force_original_aspect_ratio=increase,"
            "crop=512:512,"
            "boxblur=8:1,"
            "eq=contrast=0.68:brightness=0.12:saturation=0.85,"
            "vignette=angle=0.45"
        )

        # 3. АУДИО-ФИЛЬТР
        #
        # aresample=11025
        #     ↓
        #     намеренно ухудшаем качество звука
        #
        # aresample=44100
        #     ↓
        #     возвращаем частоту обратно
        #
        # highpass / lowpass
        #     ↓
        #     убираем часть частот
        #
        # acompressor
        #     ↓
        #     сильно сжимаем динамический диапазон
        #
        # overdrive
        #     ↓
        #     лёгкий цифровой перегруз/искажение
        #
        # volume
        #     ↓
        #     немного увеличиваем громкость

        af_chain = (
            "aresample=11025,"
            "aresample=44100,"
            "highpass=f=180,"
            "lowpass=f=6500,"
            "acompressor="
            "threshold=0.25:"
            "ratio=6:"
            "attack=5:"
            "release=80:"
            "makeup=2,"
            "overdrive=drive=6:colour=20,"
            "volume=1.15"
        )

        # 4. FFmpeg
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',
            '-i', input_path,

            # Видео
            '-vf', vf_chain,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '26',

            # Звук
            '-af', af_chain,
            '-c:a', 'aac',
            '-b:a', '64k',

            # Выход
            output_path
        ]

        subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )

        # 5. Отправка результата
        with open(output_path, 'rb') as video_note:
            bot.send_video_note(
                chat_id,
                video_note
            )

        # Удаляем сообщение "Обрабатываю..."
        bot.delete_message(
            chat_id,
            status_msg.message_id
        )

    except Exception as e:
        bot.send_message(
            chat_id,
            f"Произошла ошибка при обработке: {e}"
        )

    finally:
        # 6. Чистка файлов
        if os.path.exists(input_path):
            os.remove(input_path)

        if os.path.exists(output_path):
            os.remove(output_path)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port
    )
