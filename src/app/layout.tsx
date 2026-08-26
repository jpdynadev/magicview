import type { Metadata } from "next";
import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";
import type { ReactNode } from "react";

import { Providers } from "@/app/providers";

import "./globals.css";

const sansFont = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-sans",
});

const monoFont = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Kinnan Optimization Lab | MagicView",
  description: "A controlled cEDH experiment log searching for the best-supported Kinnan 99 through paired Forge and Manabrew simulation.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={`${sansFont.variable} ${monoFont.variable}`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
