"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

interface CurrencyToggleProps<T extends string> {
  options: readonly { value: T; label: string }[];
  // null when nothing is selected (e.g. a product whose currency hasn't been
  // inferred yet) — the pill is hidden then.
  value: T | null;
  onChange: (next: T) => void;
}

// Issue #63 — segmented currency picker with a sliding pill, shared by the
// Add Item dialog (with "Auto") and the sheet's edit mode (without — the
// backend can't reset a currency back to undetected).
function CurrencyToggle<T extends string>({ options, value, onChange }: CurrencyToggleProps<T>) {
  const index = options.findIndex((option) => option.value === value);
  return (
    <ToggleGroup
      spacing={0}
      // Equal-width columns for any option count (the pill's width and
      // translateX are expressed in whole columns).
      className="relative grid grid-flow-col auto-cols-fr"
      value={value === null ? [] : [value]}
      // Single-select Base UI group: clicking the active item yields [] —
      // ignored, so a selected currency can't be cleared by clicking it.
      onValueChange={(next) => {
        if (next[0]) onChange(next[0] as T);
      }}
    >
      {index >= 0 && (
        <div
          aria-hidden
          className="absolute inset-y-0 left-0 rounded-lg bg-muted transition-transform duration-200 ease-out motion-reduce:transition-none"
          style={{ width: `${100 / options.length}%`, transform: `translateX(${index * 100}%)` }}
        />
      )}
      {options.map((option) => (
        <ToggleGroupItem key={option.value} value={option.value} className="relative z-10 text-xs hover:bg-transparent aria-pressed:bg-transparent">
          {option.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

export { CurrencyToggle };
