import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { AuthProvider } from "@/hooks/use-auth";
import { THEME_STORAGE_KEY, ThemeProvider } from "@/hooks/use-theme";

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

// Runs before paint so the stored/OS theme never flashes the wrong colours.
const themeScript = `(function(){try{var s=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});var d=s==='dark'||((s===null||s==='system')&&window.matchMedia('(prefers-color-scheme: dark)').matches);var r=document.documentElement;r.classList.toggle('dark',d);r.style.colorScheme=d?'dark':'light';}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body suppressHydrationWarning>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
