"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AlertCircle, Mic } from "lucide-react";
import type { ErrorType } from "@/types";

interface ErrorBannerProps {
  error: ErrorType;
  onReconnect: () => void;
  onDismiss: () => void;
}

export function ErrorBanner({ error, onReconnect, onDismiss }: ErrorBannerProps) {
  if (!error) return null;

  if (error === "mic-denied") {
    return (
      <Alert variant="destructive" className="mb-4 max-w-lg">
        <Mic className="size-4" />
        <AlertTitle>Microphone access denied</AlertTitle>
        <AlertDescription>
          Please allow microphone access in your browser settings and try again.
        </AlertDescription>
        <div className="mt-2">
          <Button variant="outline" size="sm" onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      </Alert>
    );
  }

  const message =
    error === "disconnected"
      ? "Connection lost. Please check your connection."
      : "Session error. Please try again.";

  return (
    <Alert variant="destructive" className="mb-4 max-w-lg">
      <AlertCircle className="size-4" />
      <AlertTitle>{error === "disconnected" ? "Disconnected" : "Error"}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
      <div className="mt-2">
        <Button variant="outline" size="sm" onClick={onReconnect}>
          Reconnect
        </Button>
      </div>
    </Alert>
  );
}
