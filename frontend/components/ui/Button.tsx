"use client";

import type { ButtonHTMLAttributes } from "react";

type Variant = "buy" | "sell" | "submit" | "ghost";

const VARIANTS: Record<Variant, string> = {
  buy: "bg-up/15 text-up-text border-up/40 hover:bg-up/25",
  sell: "bg-down/15 text-down-text border-down/40 hover:bg-down/25",
  submit: "bg-purple text-white border-purple hover:brightness-110",
  ghost: "bg-transparent text-text-muted border-border hover:text-text hover:border-border-bright",
};

export function Button({
  variant = "ghost",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      className={`rounded border px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${className}`}
    />
  );
}
