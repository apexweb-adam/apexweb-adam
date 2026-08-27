import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Apex Trading Platform",
  description: "Multi-market paper trading CRM with AI learning",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
