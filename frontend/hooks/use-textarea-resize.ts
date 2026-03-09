import { useCallback, useEffect, useRef } from "react";

export function useTextareaResize(value: string, minRows = 1) {
  const ref = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    const lineHeight = parseInt(getComputedStyle(el).lineHeight) || 20;
    const minH = lineHeight * minRows;
    const maxH = lineHeight * 8;
    el.style.height = `${Math.min(Math.max(el.scrollHeight, minH), maxH)}px`;
    el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden";
  }, [minRows]);

  useEffect(() => {
    resize();
  }, [value, resize]);

  return ref;
}
