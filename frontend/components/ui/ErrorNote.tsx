"use client";

import type { ReactNode } from "react";

/** How a failed action reports itself, wherever it happens. */
export function ErrorNote({
  children,
  testId,
  className = "",
}: {
  children: ReactNode;
  testId?: string;
  className?: string;
}) {
  return (
    <p
      role="alert"
      data-testid={testId}
      className={`rounded-control bg-down-wash px-3 py-2 text-[12px] font-medium text-down-text ${className}`}
    >
      {children}
    </p>
  );
}
