"use client";

import type { ButtonHTMLAttributes } from "react";

type Variant = "prominent" | "buy" | "sell" | "tinted" | "gray" | "plain";

/**
 * The platform's button set.
 *
 * Apple distinguishes buttons by fill weight rather than by shape: prominent
 * actions are filled with a system colour, secondary ones take that colour as
 * a tint, and everything else is grey or bare. Blue is the interaction fill —
 * green and red are reserved for buy and sell, which are the only two places
 * in the app where the direction colours name an action rather than a number.
 *
 * Pressed state dims rather than scales, which is the platform's own feedback.
 */
const VARIANTS: Record<Variant, string> = {
  prominent: "bg-blue-fill text-white hover:brightness-110",
  buy: "bg-up-fill text-white hover:brightness-110",
  sell: "bg-down-fill text-white hover:brightness-110",
  tinted: "bg-blue-wash text-blue-text hover:brightness-95 dark:hover:brightness-125",
  gray: "bg-surface-sunk text-text hover:brightness-95 dark:hover:brightness-125",
  plain: "bg-transparent text-blue-text hover:bg-surface-sunk",
};

export function Button({
  variant = "gray",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      className={`rounded-control px-4 py-2 text-[13px] font-semibold tracking-[-0.01em]
        transition active:opacity-70 disabled:pointer-events-none disabled:opacity-40
        ${VARIANTS[variant]} ${className}`}
    />
  );
}
