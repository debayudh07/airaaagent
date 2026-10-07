import type { Metadata } from "next";
import type { ReactNode } from "react";

// Shared links are private by intent: keep them out of search results and do not leak the URL as a referrer.
export const metadata: Metadata = {
  title: "Shared with you · airaa",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
