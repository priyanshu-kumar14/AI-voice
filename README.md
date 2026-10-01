# F5-TTS Voice Studio

A zero-shot text-to-speech app with a FastAPI + F5-TTS backend and a Next.js
frontend. The backend stores generated WAV files in its local output directory.

## Directory structure

```
f5tts-firebase-app/
├── backend/
│   ├── main.py                  # FastAPI app: /upload, /generate, /history
│   ├── requirements.txt
│   ├── .env.example
│   ├── serviceAccountKey.json   # <- you add this (not committed)
│   ├── temp_uploads/            # created at runtime
│   └── temp_outputs/            # created at runtime
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Generation UI + History panel
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── tsconfig.json
│   └── .env.local.example
└── README.md
```

## Local setup

```bash
# Create and activate the environment
conda create -n f5tts-backend python=3.10 -y
conda activate f5tts-backend

cd backend

# (Apple Silicon) install the PyTorch build with MPS support
pip install --pre torch torchaudio --extra-index-url https://download.pytorch.org/whl/nightly/cpu
# On most setups the regular pip install of torch already ships MPS support
# on macOS 12.3+; the extra-index line above is only needed if the default
# wheel doesn't expose backends.mps.

# Install the rest of the dependencies (includes f5-tts, firebase-admin, fastapi)
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# edit .env: set REFERENCE_VOICE_PATH and CORS_ORIGINS

# Run the API
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The app auto-detects hardware: it uses `mps` on Apple Silicon if available,
falls back to `cuda`, then `cpu`. You'll see the selected device printed on
startup, e.g. `[F5-TTS] Using device: mps`.

First run will download the F5-TTS base model checkpoint automatically
(cached under `~/.cache`), so expect a delay on the very first `/generate`
call.

## Frontend setup

```bash
cd frontend
npm install

cp .env.local.example .env.local
# set NEXT_PUBLIC_API_BASE_URL to the deployed backend URL

npm run dev
```

Visit http://localhost:3000.

## Deploy with containers

Build and run the backend, mounting the reference WAV and passing the deployed
frontend origin:

```bash
docker build -t f5tts-backend ./backend
docker run --rm -p 8000:8000 \
  -e REFERENCE_VOICE_PATH=/app/reference_voice.wav \
  -e CORS_ORIGINS=https://your-frontend.example.com \
  -v "$PWD/reference_voice.wav:/app/reference_voice.wav:ro" \
  f5tts-backend
```

Build the frontend with the backend URL available at build time, then run it:

```bash
docker build --build-arg NEXT_PUBLIC_API_BASE_URL=https://your-backend.example.com -t f5tts-frontend ./frontend
docker run --rm -p 3000:3000 f5tts-frontend
```

For the frontend Docker build, `NEXT_PUBLIC_API_BASE_URL` must be available to
Next.js during `npm run build`; use an environment-specific `.env.production`
or add an `ARG`/`ENV` pair to the frontend Dockerfile for your platform.

## Using the app

1. Pick a short, clean `.wav` reference clip of the voice to clone
   (a few seconds of clear speech works best).
2. Optionally provide the transcript of that reference clip — this
   improves F5-TTS's alignment quality.
3. Type the script you want spoken in the cloned voice.
4. Click **Generate**. The backend will:
   - save your uploaded reference file locally,
   - run `f5tts.infer()` on the chosen device,
  - write the resulting `.wav` to the backend output directory,
  - return a URL for the generated file to the frontend.

## Production notes

- Set `CORS_ORIGINS` to the exact frontend origin, without a trailing slash.
- Set `REFERENCE_VOICE_PATH` to a mounted WAV file; it is intentionally not
  committed to the repository.
- Generated files are local and ephemeral. Use persistent storage or signed
  object-storage URLs if files must survive restarts or multiple replicas.
- `/generate` is unauthenticated. Add authentication and rate limiting before
  exposing it publicly.
