import type { Metadata } from "next";
import "./globals.css";
import { brittiSans, ndot } from "./fonts";
import { cn } from "@/lib/utils";
import Nav from "@/components/nav";
import { NavSlotProvider } from "@/components/nav-slot";
import { Toaster } from "@/components/ui/toast";

export const metadata: Metadata = {
  title: "youn-server",
  description: "Personal price and stock alert dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={cn("dark font-sans", brittiSans.variable, ndot.variable)}
    >
      <body className="antialiased">
        <NavSlotProvider>
          <Nav />
          {children}
        </NavSlotProvider>
        <Toaster />
      </body>
    </html>
  );
}
