import * as React from "react";
import { cn } from "@/lib/utils";

function Item({
  className,
  variant = "default",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { variant?: "default" | "muted" }) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors",
        variant === "default" && "bg-card border border-border",
        variant === "muted" && "bg-secondary/50 border border-border/50",
        className,
      )}
      {...props}
    />
  );
}

function ItemMedia({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex shrink-0 items-center justify-center", className)} {...props} />;
}

function ItemContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex min-w-0 flex-1 flex-col justify-center", className)} {...props} />;
}

function ItemTitle({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("text-xs font-medium leading-tight text-foreground", className)} {...props} />;
}

function ItemDescription({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("text-[10px] text-muted-foreground leading-tight mt-0.5", className)} {...props} />;
}

export { Item, ItemMedia, ItemContent, ItemTitle, ItemDescription };
