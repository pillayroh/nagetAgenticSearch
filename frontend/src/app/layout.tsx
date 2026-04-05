import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Roboto } from "next/font/google";
import "./globals.css";

const roboto = Roboto({
  weight: ["400", "500", "700"],
  subsets: ["latin"],
  variable: "--font-roboto",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Agentic Search",
  description: "Web-grounded search and cited tables",
};

export const viewport: Viewport = {
  themeColor: "#202124",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${roboto.variable} font-sans antialiased bg-[#202124] text-[#e8eaed]`}
        style={{ fontFamily: "var(--font-roboto), Arial, Helvetica, sans-serif" }}
      >
        {children}
      </body>
    </html>
  );
}
