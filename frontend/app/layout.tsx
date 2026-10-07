import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NoticeAlert - GST Notice Intelligence for CAs",
  description:
    "Detect GST department notices from your mailbox and dispatch WhatsApp alerts to your team and clients.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
