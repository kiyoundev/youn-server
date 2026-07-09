import localFont from "next/font/local";

export const brittiSans = localFont({
  src: [
    { path: "./fonts/BrittiSans-Light.otf", weight: "300", style: "normal" },
    { path: "./fonts/BrittiSans-Regular.otf", weight: "400", style: "normal" },
    { path: "./fonts/BrittiSans-Semibold.otf", weight: "600", style: "normal" },
    { path: "./fonts/BrittiSans-Bold.otf", weight: "700", style: "normal" },
  ],
  variable: "--font-sans",
  display: "swap",
});
