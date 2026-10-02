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
  description: "AI research agent for Web3: live market, DeFi and on-chain data in one conversation.",
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
