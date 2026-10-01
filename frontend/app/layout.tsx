import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "F5-TTS Studio",
  description: "Zero-shot text-to-speech with F5-TTS + Firebase",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
