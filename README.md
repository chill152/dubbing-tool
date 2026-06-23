# 🎙 AI Dubbing Tool — Trung → Việt

Tự động lồng tiếng video tiếng Trung sang tiếng Việt bằng AI.

## Tính năng
- Tải video từ YouTube, TikTok, Douyin
- Nhận dạng giọng nói tiếng Trung (Whisper ASR)
- Dịch tự động bằng Claude AI
- Tổng hợp giọng nói tiếng Việt (Edge TTS)
- Ghép audio vào video gốc

## Cài đặt

```bash
pip install -r requirements.txt
```

## Sử dụng

1. Mở file `server.py`, điền API key Anthropic vào dòng `ANTHROPIC_API_KEY`
2. Chạy server:
```bash
python server.py
```
3. Mở `index.html` trong trình duyệt
4. Dán URL video → nhấn **Bắt đầu xử lý**

## Yêu cầu
- Python 3.10+
- FFmpeg (cài riêng)
- API key Anthropic: https://console.anthropic.com

