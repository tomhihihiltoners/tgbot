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
        # ============================================================
        # 1. СКАЧИВАЕМ ВИДЕО
        # ============================================================

        file_id = (
            message.video_note.file_id
            if message.video_note
            else message.video.file_id
        )

        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open(input_path, 'wb') as f:
            f.write(downloaded_file)

        # ============================================================
        # 2. ФИЛЬТР ВИДЕО
        # ============================================================

        vf_chain = (
            "scale=512:512:force_original_aspect_ratio=increase,"
            "crop=512:512,"
            "boxblur=8:1,"
            "eq=contrast=0.68:brightness=0.12:saturation=0.85,"
            "vignette=angle=0.45"
        )

        # ============================================================
        # 3. ФИЛЬТР ЗВУКА
        # ============================================================
        #
        # Делаем звук похожим на плохой/перегруженный микрофон:
        #
        # aresample=11025
        #     ↓
        #     искусственно ухудшаем исходный звук
        #
        # aresample=44100
        #     ↓
        #     возвращаем стандартную частоту
        #
        # highpass=180
        #     ↓
        #     убираем очень низкие частоты
        #
        # lowpass=6500
        #     ↓
        #     убираем верхние частоты
        #
        # acompressor
        #     ↓
        #     сильно сжимаем звук
        #
        # alimiter
        #     ↓
        #     ограничиваем пики и создаём эффект
        #     слегка перегруженного микрофона
        #
        # volume
        #     ↓
        #     немного увеличиваем громкость

        af_chain = (
            "aresample=6000,"
            "aresample=44100,"
            "highpass=f=350,"
            "lowpass=f=3000,"
            "acompressor="
            "threshold=0.12:"
            "ratio=20:"
            "attack=1:"
            "release=25:"
            "makeup=7,"
            "acrusher="
            "bits=5:"
            "mix=1:"
            "mode=lin,"
            "acrusher="
            "bits=6:"
            "mix=0.65:"
            "mode=lin,"
            "alimiter=limit=0.55,"
            "volume=1.8"
            )

        # ============================================================
        # 4. FFmpeg
        # ============================================================

        ffmpeg_cmd = [
            'ffmpeg',
            '-y',

            # Вход
            '-i', input_path,

            # ---------------- VIDEO ----------------

            '-vf', vf_chain,

            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '26',

            # ---------------- AUDIO ----------------

            '-af', af_chain,

            '-c:a', 'aac',
            '-b:a', '64k',

            # ---------------- OUTPUT ----------------

            output_path
        ]

        # Запускаем FFmpeg.
        # stderr сохраняем, чтобы при ошибке видеть причину.

        result = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # ============================================================
        # 5. ПРОВЕРЯЕМ FFmpeg
        # ============================================================

        if result.returncode != 0:

            # Берём последние строки ошибки FFmpeg
            error_log = result.stderr[-3000:]

            print("========== FFMPEG ERROR ==========")
            print(error_log)
            print("==================================")

            raise Exception(
                f"FFmpeg завершился с ошибкой.\n\n{error_log}"
            )

        # ============================================================
        # 6. ПРОВЕРЯЕМ, ЧТО ФАЙЛ СОЗДАЛСЯ
        # ============================================================

        if not os.path.exists(output_path):
            raise Exception(
                "FFmpeg не создал выходной файл."
            )

        # ============================================================
        # 7. ОТПРАВЛЯЕМ РЕЗУЛЬТАТ
        # ============================================================

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

    # ================================================================
    # 8. ОБРАБОКА ОШИБКИ
    # ================================================================

    except Exception as e:

        print("========== ERROR ==========")
        print(e)
        print("============================")

        bot.send_message(
            chat_id,
            f"Произошла ошибка при обработке:\n\n{e}"
        )

    # ================================================================
    # 9. УДАЛЯЕМ ВРЕМЕННЫЕ ФАЙЛЫ
    # ================================================================

    finally:

        if os.path.exists(input_path):
            os.remove(input_path)

        if os.path.exists(output_path):
            os.remove(output_path)


# ====================================================================
# ЗАПУСК FLASK
# ====================================================================

if __name__ == '__main__':

    port = int(
        os.getenv('PORT', 5000)
    )

    app.run(
        host='0.0.0.0',
        port=port
    )
