import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Loomi — Organizational Memory Briefing',
  description: 'Proactive organizational knowledge discovery, retention, and onboarding assistant.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
