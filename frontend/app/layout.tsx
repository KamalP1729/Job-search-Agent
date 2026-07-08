import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Job Agent",
  description: "Agentic job search, end to end",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} min-h-screen bg-[#030712] text-white antialiased`}>
        <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none" aria-hidden="true">
          <div className="absolute -top-96 -right-48 w-[800px] h-[800px] rounded-full bg-indigo-500/20 blur-[120px]" />
          <div className="absolute -bottom-96 -left-48 w-[800px] h-[800px] rounded-full bg-violet-600/[0.15] blur-[120px]" />
          <div className="absolute top-1/3 left-1/4 w-[600px] h-[600px] rounded-full bg-blue-600/10 blur-[100px]" />
        </div>
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
