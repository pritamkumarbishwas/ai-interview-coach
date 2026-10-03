import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { AuthProvider } from "@/hooks/use-auth";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "AI Interview Coach",
    template: "%s · AI Interview Coach",
  },
  description:
    "Practice realistic AI-powered mock interviews, get evaluated after every answer, and receive a personal preparation plan.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
