"use client";

import type { ButtonHTMLAttributes } from "react";

type Variant = "buy" | "sell" | "submit" | "ghost" | "quiet";

// Pill buttons, filled only where the action is the point. eToro's buy and
// sell are the two loudest controls on the screen and everything else steps
// back from them.
const VARIANTS: Record<Variant, string> = {
  buy: "bg-brand text-white shadow-sm hover:bg-brand-deep active:scale-[0.98]",
  sell: "bg-down text-white shadow-sm hover:brightness-95 active:scale-[0.98]",
  submit: "bg-text text-white hover:bg-rail active:scale-[0.98]",
  ghost: "bg-surface-sunk text-text hover:bg-border",
  quiet: "bg-transparent text-text-muted hover:bg-surface-sunk hover:text-text",
};

export function Button({
  variant = "ghost",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      className={`rounded-full px-4 py-2 font-display text-[13px] font-bold tracking-tight transition disabled:cursor-not-allowed disabled:bg-surface-sunk disabled:text-text-faint disabled:shadow-none disabled:active:scale-100 ${VARIANTS[variant]} ${className}`}
    />
  );
}
