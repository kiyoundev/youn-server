"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

type NavSlotContextValue = {
  slotEl: HTMLDivElement | null;
  setSlotEl: (el: HTMLDivElement | null) => void;
};

const NavSlotContext = createContext<NavSlotContextValue | null>(null);

export function NavSlotProvider({ children }: { children: ReactNode }) {
  const [slotEl, setSlotEl] = useState<HTMLDivElement | null>(null);
  return <NavSlotContext.Provider value={{ slotEl, setSlotEl }}>{children}</NavSlotContext.Provider>;
}

function useNavSlotContext() {
  const ctx = useContext(NavSlotContext);
  if (!ctx) throw new Error("useNavSlotContext must be used within NavSlotProvider");
  return ctx;
}

// Nav calls this to register the DOM node it owns for the current route —
// pages portal their own search/action controls into it. Passed directly as
// a ref callback, so unmounting the node auto-clears the registration.
export function useNavSlotRegistration() {
  return useNavSlotContext().setSlotEl;
}

// Pages call this to get the node to portal their controls into. Null until
// Nav has mounted the slot for the current route.
export function useNavSlot() {
  return useNavSlotContext().slotEl;
}
