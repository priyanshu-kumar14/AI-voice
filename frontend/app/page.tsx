"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function Home() {
  const [targetText, setTargetText] = useState("");
  const [outputFilename, setOutputFilename] = useState("generated_voice.wav");
  const [isGenerating, setIsGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setError(null);
    setAudioUrl(null);

    if (!targetText.trim()) {
      setError("Please enter the text you want spoken.");
      return;
    }

    setIsGenerating(true);
    try {
      const formData = new FormData();
      formData.append("target_text", targetText);
      formData.append("output_filename", outputFilename);

      const response = await fetch(`${API_BASE}/generate`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Generation failed");
      }

      const { audio_url } = await response.json();
      setAudioUrl(`${API_BASE}${audio_url}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reach the backend.");
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-3xl px-6 py-10">
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl">
          <h1 className="mb-1 text-2xl font-semibold">F5-TTS Voice Studio</h1>
          <p className="mb-6 text-sm text-slate-400">
            Use one reference voice to convert text into speech locally.
          </p>

          <div className="space-y-5">
            <p className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-3 text-sm text-slate-300">
              Fixed voice: Isla, youthful, relaxed, and warm
            </p>

            <div>
              <label className="mb-2 block text-sm font-medium">Text to speak</label>
              <textarea
                value={targetText}
                onChange={(event) => setTargetText(event.target.value)}
                rows={6}
                placeholder="Type the text to convert into the reference voice..."
                className="w-full resize-none rounded-lg border border-slate-700 bg-slate-800 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium">Output filename</label>
              <input
                type="text"
                value={outputFilename}
                onChange={(event) => setOutputFilename(event.target.value)}
                placeholder="generated_voice.wav"
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            {error && (
              <p className="rounded-lg border border-red-900 bg-red-950/40 px-3 py-2 text-sm text-red-400">
                {error}
              </p>
            )}

            <button
              onClick={handleGenerate}
              disabled={isGenerating}
              className="w-full rounded-lg bg-indigo-600 py-3 font-medium transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {isGenerating ? "Generating speech..." : "Generate speech"}
            </button>

            {audioUrl && (
              <div className="rounded-xl border border-emerald-900 bg-emerald-950/30 p-4">
                <p className="mb-2 text-sm font-medium text-emerald-300">Generated speech</p>
                <audio controls className="w-full" src={audioUrl} />
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
