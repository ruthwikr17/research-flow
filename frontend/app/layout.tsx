import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "ResearchFlow", description: "Autonomous research system" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

