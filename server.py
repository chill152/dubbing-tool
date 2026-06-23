import os, subprocess, json, asyncio, uuid, shutil
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import whisper
import anthropic
import edge_tts

app = Flask(__name__, static_folder=".")
CORS(app)

ANTHROPIC_API_KEY = "sk-ant-xxxxxxxx"  # <-- Dán API key của bạn vào đây
OUTPUT_DIR = "./output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── BƯỚC 1: Tải video ───────────────────────────────────────────────
def download_video(url, job_id):
    out_path = f"{OUTPUT_DIR}/{job_id}/video.mp4"
    os.makedirs(f"{OUTPUT_DIR}/{job_id}", exist_ok=True)
    subprocess.run([
        "yt-dlp", "-f", "best[ext=mp4]/best",
        "-o", out_path, url
    ], check=True)
    return out_path

# ─── BƯỚC 2: Tách âm thanh ───────────────────────────────────────────
def extract_audio(video_path, job_id):
    audio_path = f"{OUTPUT_DIR}/{job_id}/audio.wav"
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-ac", "1", "-ar", "16000",
        "-vn", audio_path, "-y"
    ], check=True)
    return audio_path

# ─── BƯỚC 3: Nhận dạng giọng nói (ASR Whisper) ──────────────────────
def transcribe_audio(audio_path):
    model = whisper.load_model("base")  # Dùng "small" hoặc "medium" để chính xác hơn
    result = model.transcribe(audio_path, language="zh")
    segments = result["segments"]
    return segments  # [{start, end, text}, ...]

# ─── BƯỚC 4: Dịch Trung → Việt bằng Claude AI ───────────────────────
def translate_segments(segments):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    texts_zh = [s["text"].strip() for s in segments]
    
    prompt = f"""Dịch các câu tiếng Trung sau sang tiếng Việt tự nhiên, phù hợp cho lồng tiếng video.
Trả về JSON array với format: [{{"zh":"...","vi":"..."}}]
Chỉ trả về JSON, không giải thích thêm.

{json.dumps(texts_zh, ensure_ascii=False)}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    pairs = json.loads(raw)
    
    # Gắn bản dịch vào segments
    for i, seg in enumerate(segments):
        seg["vi"] = pairs[i]["vi"] if i < len(pairs) else seg["text"]
    return segments

# ─── BƯỚC 5: Tổng hợp giọng nói tiếng Việt (TTS) ───────────────────
async def synthesize_tts(segments, job_id, voice="female"):
    voice_name = "vi-VN-HoaiMyNeural" if voice == "female" else "vi-VN-NamMinhNeural"
    tts_files = []
    
    for i, seg in enumerate(segments):
        out_file = f"{OUTPUT_DIR}/{job_id}/tts_{i:03d}.mp3"
        communicate = edge_tts.Communicate(seg["vi"], voice_name)
        await communicate.save(out_file)
        tts_files.append({
            "file": out_file,
            "start": seg["start"],
            "end": seg["end"]
        })
    return tts_files

# ─── BƯỚC 6: Ghép giọng vào video ───────────────────────────────────
def merge_audio_video(video_path, tts_files, job_id):
    # Tạo file audio timeline từ các đoạn TTS
    filter_parts = []
    input_args = ["-i", video_path]
    
    for i, t in enumerate(tts_files):
        input_args += ["-i", t["file"]]
        filter_parts.append(
            f"[{i+1}:a]adelay={int(t['start']*1000)}|{int(t['start']*1000)}[a{i}]"
        )
    
    if filter_parts:
        mix_inputs = "".join(f"[a{i}]" for i in range(len(tts_files)))
        filter_complex = ";".join(filter_parts) + f";[0:a]{mix_inputs}amix=inputs={len(tts_files)+1}:normalize=0[aout]"
        output_path = f"{OUTPUT_DIR}/{job_id}/output_dubbed.mp4"
        
        cmd = ["ffmpeg", *input_args,
               "-filter_complex", filter_complex,
               "-map", "0:v", "-map", "[aout]",
               "-c:v", "copy", "-c:a", "aac",
               output_path, "-y"]
        subprocess.run(cmd, check=True)
        return output_path
    return video_path

# ─── API ENDPOINT CHÍNH ───────────────────────────────────────────────
@app.route("/api/dub", methods=["POST"])
def dub_video():
    data = request.json
    url = data.get("url", "")
    voice = data.get("voice", "female")
    job_id = str(uuid.uuid4())[:8]
    
    try:
        print(f"[{job_id}] Bắt đầu xử lý: {url}")
        
        # Bước 1
        video_path = download_video(url, job_id)
        print(f"[{job_id}] ✓ Tải video xong")
        
        # Bước 2
        audio_path = extract_audio(video_path, job_id)
        print(f"[{job_id}] ✓ Tách âm xong")
        
        # Bước 3
        segments = transcribe_audio(audio_path)
        print(f"[{job_id}] ✓ ASR xong - {len(segments)} đoạn")
        
        # Bước 4
        segments = translate_segments(segments)
        print(f"[{job_id}] ✓ Dịch xong")
        
        # Bước 5
        tts_files = asyncio.run(synthesize_tts(segments, job_id, voice))
        print(f"[{job_id}] ✓ TTS xong")
        
        # Bước 6
        output_path = merge_audio_video(video_path, tts_files, job_id)
        print(f"[{job_id}] ✓ Ghép video xong")
        
        # Tạo transcript
        transcript = [{"zh": s["text"], "vi": s["vi"], "start": s["start"], "end": s["end"]} for s in segments]
        
        return jsonify({
            "success": True,
            "job_id": job_id,
            "output": output_path,
            "transcript": transcript
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/download/<job_id>")
def download_file(job_id):
    return send_from_directory(f"{OUTPUT_DIR}/{job_id}", "output_dubbed.mp4", as_attachment=True)

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    print("🚀 Server đang chạy tại http://localhost:5000")
    app.run(debug=True, port=5000)
