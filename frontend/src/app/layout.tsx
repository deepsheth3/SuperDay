import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Harper Agent",
  description: "Chat with Harper — memory agent for accounts and status.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col font-sans">
        {children}
      </body>
    </html>
  );
}
