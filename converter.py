import os
from dotenv import load_dotenv
import os
import subprocess
import uuid
import shutil
from flask import Flask, render_template, request, send_file, jsonify
import requests
from datetime import datetime, timedelta
import threading
import time



load_dotenv()


# Создаем приложение Flask
app = Flask(__name__)

# Конфигурация
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'output'
app.config['MAX_SIZE_MB'] = 500
app.config['FILE_LIFETIME_MINUTES'] = 30
# Создаем папки для файлов
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)


app.config['API_KEY'] = os.getenv("CONVERTER_API_KEY", "default_secret_key")
# Проверка наличия FFmpeg
def check_ffmpeg():
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        return "ffmpeg version" in result.stdout
    except:
        return False

# Функция очистки старых файлов
def cleanup_old_files():
    while True:
        try:
            now = datetime.now()
            for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
                for filename in os.listdir(folder):
                    filepath = os.path.join(folder, filename)
                    file_time = datetime.fromtimestamp(os.path.getctime(filepath))
                    if now - file_time > timedelta(minutes=app.config['FILE_LIFETIME_MINUTES']):
                        os.remove(filepath)
                        print(f"Удален старый файл: {filename}")
        except Exception as e:
            print(f"Ошибка очистки файлов: {e}")
        time.sleep(60 * 5)  # Проверка каждые 5 минут

# Запускаем очистку в фоновом потоке
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

@app.route('/')
def index():
    ffmpeg_installed = check_ffmpeg()
    return render_template('index.html',
                           ffmpeg_ok=ffmpeg_installed,
                           max_size=app.config['MAX_SIZE_MB'])

@app.route('/convert', methods=['POST'])
def convert_video():
    if 'video' not in request.files:
        return "Файл не выбран", 400

    video_file = request.files['video']
    if video_file.filename == '':
        return "Неверное имя файла", 400

    try:
        unique_id = str(uuid.uuid4())
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{unique_id}_{video_file.filename}")
        audio_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{unique_id}.mp3")

        video_file.save(video_path)

        command = f'ffmpeg -i "{video_path}" -q:a 0 -map a "{audio_path}"'
        subprocess.run(command, shell=True, check=True)

        os.remove(video_path)

        return send_file(audio_path, as_attachment=True)

    except Exception as e:
        if 'video_path' in locals() and os.path.exists(video_path):
            os.remove(video_path)
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)
        return f"Ошибка конвертации: {str(e)}", 500


@app.route('/api/convert', methods=['POST'])
def api_convert_video():
    # Проверка API ключа
    if request.headers.get('X-API-KEY') != app.config['API_KEY']:
        return jsonify({"error": "Unauthorized"}), 401

    if 'video' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({"error": "Invalid filename"}), 400

    try:
        unique_id = str(uuid.uuid4())
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{unique_id}_{video_file.filename}")
        audio_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{unique_id}.mp3")

        video_file.save(video_path)

        # Логирование для отладки
        print(f"Конвертация: {video_path} -> {audio_path}")

        # Исправленная команда FFmpeg (убираем кавычки для Linux)
        command = f'ffmpeg -i {video_path} -q:a 0 -map a {audio_path}'
        result = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            error_msg = f"FFmpeg error: {result.stderr[:200]}"
            print(error_msg)
            return jsonify({"error": error_msg}), 500

        os.remove(video_path)

        return jsonify({
            "success": True,
            "audio_url": f"/download/{unique_id}",
            "file_id": unique_id
        })

    except Exception as e:
        print(f"Ошибка конвертации: {str(e)}")
        if 'video_path' in locals() and os.path.exists(video_path):
            os.remove(video_path)
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)
        return jsonify({"error": str(e)}), 500

@app.route('/download/<file_id>', methods=['GET'])
def download_audio(file_id):
    audio_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{file_id}.mp3")
    if os.path.exists(audio_path):
        return send_file(audio_path, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    print("Проверка установки FFmpeg...")
    if check_ffmpeg():
        print("FFmpeg найден! Сервер запускается")
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        print("ОШИБКА: FFmpeg не установлен или не добавлен в PATH")
