import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Blix — Think destination, not routes",
  description:
    "AI-powered public transport assistant for Delhi government buses.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
