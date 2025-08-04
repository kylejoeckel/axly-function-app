import base64
from io import BytesIO
import openai

def transcribe_audio(audio_bytes):
    header = audio_bytes[:12]
    if header[:3] == b"ID3": ext = "mp3"
    elif header[4:8] == b"ftyp": ext = "m4a"
    elif header[:4] == b"RIFF" and header[8:12] == b"WAVE": ext = "wav"
    elif header[:4] == b"OggS": ext = "ogg"
    elif header[:4] == b"fLaC": ext = "flac"
    elif header[:4] == b"\x1A\x45\xDF\xA3": ext = "webm"
    else: raise ValueError("Unsupported audio format")

    buf = BytesIO(audio_bytes)
    buf.name = f"clip.{ext}"

    result = openai.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
        response_format="text"
    )
    return result, ext
