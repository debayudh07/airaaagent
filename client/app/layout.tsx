import type { Metadata } from "next";
import { Oxanium, Noto_Sans_JP, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import Providers from "./providers";

const display = Oxanium({
  variable: "--font-display",
  subsets: ["latin"],
});

const jp = Noto_Sans_JP({
  variable: "--font-jp",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AIRAA Research Agent",
  description: "Anime-inspired Web3 intelligence chat interface",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${jp.variable} ${mono.variable} antialiased`}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
