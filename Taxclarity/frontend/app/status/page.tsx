"use client";

import { useEffect, useState } from "react";

function getApiUrl(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  if (env) return env;
  if (typeof window === "undefined") return "http://localhost:8006";
  return `${window.location.protocol}//${window.location.hostname}:8006`;
}

export default function StatusPage() {
  const [backend, setBackend] = useState<"checking" | "ok" | "error">("checking");
  const [details, setDetails] = useState<string>("");

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4000);
    fetch(`${getApiUrl()}/health`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => {
        setBackend("ok");
        setDetails(text.trim());
      })
      .catch((err) => {
        setBackend("error");
        setDetails(String(err?.message || err));
      })
      .finally(() => window.clearTimeout(timeout));
    return () => controller.abort();
  }, []);

  return (
    <main className="min-h-screen bg-[#070b16] text-slate-100 flex items-center justify-center px-6">
      <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-white/5 p-6 shadow-[0_20px_60px_rgba(0,0,0,0.35)]">
        <h1 className="text-lg font-semibold">Saul Goodman AI Status</h1>
        <p className="mt-1 text-sm text-slate-300">Frontend: OK</p>
        <div className="mt-4 rounded-xl border border-white/10 bg-black/30 p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">Backend</span>
            <span
              className={
                backend === "ok"
                  ? "text-emerald-400"
                  : backend === "error"
                    ? "text-red-400"
                    : "text-slate-400"
              }
            >
              {backend === "checking" ? "checking…" : backend}
            </span>
          </div>
          {details && (
            <pre className="mt-2 text-xs text-slate-400 whitespace-pre-wrap break-all">
              {details}
            </pre>
          )}
        </div>
        <p className="mt-4 text-xs text-slate-500">
          This page reads `NEXT_PUBLIC_API_URL` and calls `/health`.
        </p>
      </div>
    </main>
  );
}
