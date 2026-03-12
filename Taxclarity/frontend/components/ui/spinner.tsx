import * as React from "react";
import { cn } from "@/lib/utils";

interface SpinnerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "sm" | "default" | "lg";
}

function Spinner({ className, size = "default", ...props }: SpinnerProps) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={cn(
        "relative inline-flex items-center justify-center",
        size === "sm" && "h-3.5 w-3.5",
        size === "default" && "h-4 w-4",
        size === "lg" && "h-5 w-5",
        className,
      )}
      {...props}
    >
      <svg
        className="animate-spin"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <circle
          className="opacity-20"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="3"
        />
        <path
          className="opacity-75"
          d="M12 2a10 10 0 0 1 10 10"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

Spinner.displayName = "Spinner";

export { Spinner };
export type { SpinnerProps };
