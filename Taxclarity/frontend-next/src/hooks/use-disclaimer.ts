"use client";

import { useCallback, useState } from "react";

const STORAGE_KEY = "taxclarity-disclaimer-ack";

function readAcknowledgedState(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return localStorage.getItem(STORAGE_KEY) === "true";
}

export function useDisclaimer() {
  const [acknowledged, setAcknowledged] = useState(readAcknowledgedState);

  const acknowledge = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, "true");
    setAcknowledged(true);
  }, []);

  return { acknowledged, acknowledge };
}
