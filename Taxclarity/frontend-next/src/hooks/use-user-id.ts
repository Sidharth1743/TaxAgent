"use client";

import { useState } from "react";

const STORAGE_KEY = "taxclarity_user_id";

function getOrCreateUserId(): string {
  if (typeof window === "undefined") {
    return "";
  }

  let id = localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}

export function useUserId(): string {
  const [userId] = useState(getOrCreateUserId);
  return userId;
}

export function createSessionId(): string {
  return crypto.randomUUID();
}
