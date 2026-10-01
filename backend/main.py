"""F5-TTS FastAPI backend for single-reference voice cloning."""

import gc
import os
import uuid
import re
from pathlib import Path
import asyncio
import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
tts_lock = asyncio.Lock()
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "temp_uploads"
OUTPUT_DIR = BASE_DIR / "temp_outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
MAX_BATCH_CHARACTERS = int(os.environ.get("MAX_BATCH_CHARACTERS", "500"))
MAX_TEXT_CHARACTERS = int(os.environ.get("MAX_TEXT_CHARACTERS", "5000"))
REFERENCE_VOICE_PATH = Path(
    os.environ.get(
        "REFERENCE_VOICE_PATH",
        str(
            UPLOAD_DIR
            / "ElevenLabs_2026-09-18T22_18_34_Isla - Youthful, Relaxed, and Warm_eleven_v3.wav"
        ),
    )
).expanduser()


def get_cors_origins() -> list[str]:
    configured_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]

# --------------------------------------------------------------------------
# Device selection: CPU is the stable default; accelerators are opt-in.
# --------------------------------------------------------------------------


def get_device() -> str:
    requested_device = os.environ.get("F5_TTS_DEVICE", "cpu").lower()
    if requested_device in {"cpu", "mps", "cuda"}:
        if requested_device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("F5_TTS_DEVICE=mps was requested but MPS is unavailable")
        if requested_device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("F5_TTS_DEVICE=cuda was requested but CUDA is unavailable")
        return requested_device
    return "cpu"


DEVICE = get_device()
print(f"[F5-TTS] Using device: {DEVICE}")


def split_text_into_batches(text: str, max_characters: int = MAX_BATCH_CHARACTERS) -> list[str]:
    """Split near the maximum size, preferring the closest period boundary."""
    remaining = " ".join(text.split())
    batches: list[str] = []

    while len(remaining) > max_characters:
        before = remaining.rfind(".", 0, max_characters + 1)
        after = remaining.find(".", max_characters)

        if before == -1 and after == -1:
            split_at = remaining.rfind(" ", 0, max_characters + 1)
            split_at = split_at if split_at > 0 else max_characters
        elif before == -1:
            split_at = after + 1
        elif after == -1:
            split_at = before + 1
        else:
            before_distance = max_characters - (before + 1)
            after_distance = (after + 1) - max_characters
            split_at = before + 1 if before_distance <= after_distance else after + 1

        batches.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        batches.append(remaining)
    return batches


def safe_output_filename(filename: str) -> str:
    """Keep the user filename inside the output directory and use WAV output."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
    if not cleaned:
        raise HTTPException(status_code=400, detail="Please provide a valid output filename")
    return f"{Path(cleaned).stem}.wav"


def release_device_memory() -> None:
    """Release temporary tensors between sequential synthesis batches."""
    gc.collect()
    if DEVICE == "mps":
        torch.mps.synchronize()
        torch.mps.empty_cache()
    elif DEVICE == "cuda":
        torch.cuda.empty_cache()

# --------------------------------------------------------------------------
# F5-TTS model initialization
# --------------------------------------------------------------------------

from f5_tts.api import F5TTS  # noqa: E402  (import after device setup for clarity)

f5tts = F5TTS(
    model="F5TTS_v1_Base",
    device=DEVICE,
)

# --------------------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------------------

app = FastAPI(title="F5-TTS Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@app.get("/")
def root():
    return {"status": "ok", "device": DEVICE}


@app.post("/generate")
async def generate_speech(
    target_text: str = Form(...),
    output_filename: str = Form(...),
):
    """Generate speech locally using the configured fixed reference voice."""
    if not target_text.strip():
        raise HTTPException(status_code=400, detail="Text to speak cannot be empty")
    if len(target_text) > MAX_TEXT_CHARACTERS:
        raise HTTPException(
            status_code=413,
            detail=f"Text cannot exceed {MAX_TEXT_CHARACTERS} characters",
        )
    if not REFERENCE_VOICE_PATH.is_file():
        raise HTTPException(status_code=500, detail="Fixed reference voice file is missing")

    output_name = safe_output_filename(output_filename)
    output_path = OUTPUT_DIR / output_name
    batch_paths: list[Path] = []

    try:
        text_batches = split_text_into_batches(target_text)
        total_batches = len(text_batches)
        print(f"[F5-TTS] Starting {total_batches} sequential batch(es)", flush=True)
        audio_batches: list[np.ndarray] = []
        sample_rate: int | None = None
        for batch_number, text_batch in enumerate(text_batches, start=1):
            print(
                f"[F5-TTS] Batch {batch_number}/{total_batches} started "
                f"({len(text_batch)} characters)",
                flush=True,
            )
            batch_path = OUTPUT_DIR / f".{uuid.uuid4().hex}_batch_{batch_number}.wav"
            batch_paths.append(batch_path)
            async with tts_lock:
                f5tts.infer(
                    ref_file=str(REFERENCE_VOICE_PATH),
                    ref_text="",
                    gen_text=text_batch,
                    file_wave=str(batch_path),
                    remove_silence=False,
                )
            audio, current_rate = sf.read(batch_path, always_2d=True)
            if sample_rate is None:
                sample_rate = current_rate
            elif current_rate != sample_rate:
                raise RuntimeError("Generated batches use inconsistent sample rates")
            audio_batches.append(audio)
            release_device_memory()
            print(f"[F5-TTS] Batch {batch_number}/{total_batches} complete", flush=True)

        if sample_rate is None or not audio_batches:
            raise RuntimeError("No audio batches were produced")

        sf.write(output_path, np.concatenate(audio_batches, axis=0), sample_rate)

        if not output_path.exists():
            raise RuntimeError("Inference completed but no output file was produced")

        print(f"[F5-TTS] All {total_batches} batch(es) complete: {output_name}", flush=True)
        return {"audio_url": f"/audio/{output_name}", "filename": output_name}

    finally:
        for batch_path in batch_paths:
            batch_path.unlink(missing_ok=True)


@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve a generated WAV file from local storage."""
    output_path = OUTPUT_DIR / filename
    if output_path.parent != OUTPUT_DIR or not output_path.is_file():
        raise HTTPException(status_code=404, detail="Generated audio not found")
    return FileResponse(output_path, media_type="audio/wav", filename=filename)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )
