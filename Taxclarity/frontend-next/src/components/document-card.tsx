"use client";

import { useState } from "react";
import { AlertTriangle, Calculator, Check, Landmark, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type {
  DocumentComputeResponse,
  DocumentConfirmResponse,
  ExtractedDocument,
} from "@/types";

const GRAPH_API_URL =
  process.env.NEXT_PUBLIC_GRAPH_API_URL ??
  (typeof window !== "undefined" ? window.location.origin : "http://localhost:8006");

const FORM_TYPE_LABELS: Record<string, string> = {
  w2: "W-2",
  "1099": "1099",
  form16: "Form 16",
  unknown: "Unknown Form",
};

function formatFieldName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

interface DocumentCardProps {
  document: ExtractedDocument;
  userId: string;
  onConfirmed: (response?: DocumentConfirmResponse) => void;
  onDismiss: () => void;
}

export function DocumentCard({
  document,
  userId,
  onConfirmed,
  onDismiss,
}: DocumentCardProps) {
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [isConfirming, setIsConfirming] = useState(false);
  const [isComputing, setIsComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmResult, setConfirmResult] = useState<DocumentConfirmResponse | null>(null);
  const [computeResult, setComputeResult] = useState<DocumentComputeResponse | null>(null);

  const handleFieldChange = (fieldName: string, newValue: string) => {
    setCorrections((prev) => {
      // If value matches original, remove the correction
      const originalField = document.fields.find((f) => f.name === fieldName);
      if (originalField && newValue === originalField.value) {
        const next = { ...prev };
        delete next[fieldName];
        return next;
      }
      return { ...prev, [fieldName]: newValue };
    });
  };

  const handleConfirm = async () => {
    setIsConfirming(true);
    setError(null);

    try {
      const response = await fetch(
        `${GRAPH_API_URL}/api/documents/${document.doc_id}/confirm`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: userId,
            corrections: Object.keys(corrections).length > 0 ? corrections : undefined,
          }),
        }
      );

      if (!response.ok) {
        const errBody = await response.text();
        throw new Error(errBody || `Confirm failed (${response.status})`);
      }

      const result: DocumentConfirmResponse = await response.json();
      setConfirmResult(result);
      onConfirmed(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirmation failed");
    } finally {
      setIsConfirming(false);
    }
  };

  const handleCompute = async () => {
    setIsComputing(true);
    setError(null);

    try {
      const response = await fetch(
        `${GRAPH_API_URL}/api/documents/${document.doc_id}/compute`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        },
      );

      if (!response.ok) {
        const errBody = await response.text();
        throw new Error(errBody || `Compute failed (${response.status})`);
      }

      const result: DocumentComputeResponse = await response.json();
      setComputeResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Computation failed");
    } finally {
      setIsComputing(false);
    }
  };

  const formLabel = FORM_TYPE_LABELS[document.form_type] ?? document.form_type;
  const jurisdictionLabel = document.jurisdiction === "usa" ? "US" : "India";
  const canCompute = ["form16", "w2", "1099"].includes(document.form_type.toLowerCase());

  return (
    <div className="w-full max-w-2xl rounded-[28px] border border-emerald-500/25 bg-slate-900/95 shadow-[0_24px_120px_-40px_rgba(16,185,129,0.55)]">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 px-5 py-4">
        <Badge className="bg-emerald-600/20 text-emerald-300 border-emerald-600/40">
          {formLabel}
        </Badge>
        <Badge className="bg-slate-700 text-slate-300 border-slate-600">
          {jurisdictionLabel}
        </Badge>
        {confirmResult?.spanner_stored && (
          <Badge className="bg-cyan-500/15 text-cyan-300 border-cyan-500/30">
            Saved to graph
          </Badge>
        )}
        <span className="ml-auto text-xs text-slate-500">
          {document.fields.length} extracted field{document.fields.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.9fr)]">
        <div className="space-y-4">
          <div className="rounded-3xl border border-slate-800 bg-slate-950/80 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-100">Extracted fields</h3>
              <p className="text-xs text-slate-500">Review and correct before saving</p>
            </div>

            <div className="flex max-h-80 flex-col gap-2 overflow-y-auto pr-1">
              {document.fields.map((field) => (
                <div
                  key={field.name}
                  className="flex items-center gap-2 rounded-2xl border border-slate-800 bg-slate-900/80 px-3 py-2"
                >
                  <label className="w-36 shrink-0 text-xs text-slate-400 truncate" title={field.name}>
                    {formatFieldName(field.name)}
                  </label>
                  <input
                    type="text"
                    defaultValue={field.value}
                    onChange={(e) => handleFieldChange(field.name, e.target.value)}
                    className="flex-1 bg-transparent text-sm text-slate-100 focus:outline-none"
                  />
                  {field.confidence < 0.7 && (
                    <span title="Low confidence">
                      <AlertTriangle className="size-4 shrink-0 text-yellow-400" />
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {error && (
            <p className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {error}
            </p>
          )}
        </div>

        <div className="space-y-4">
          <div className="rounded-3xl border border-slate-800 bg-slate-950/80 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Landmark className="size-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-slate-100">Tax action</h3>
            </div>

            <div className="space-y-3 text-sm text-slate-300">
              <p>
                Confirm the extracted fields to persist them into the memory graph for this user.
              </p>
              {canCompute ? (
                <p className="text-slate-400">
                  This form can also be used for a direct tax estimate after confirmation.
                </p>
              ) : (
                <p className="text-slate-500">
                  This form type is stored for context, but direct tax computation is not available yet.
                </p>
              )}
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                size="sm"
                onClick={handleConfirm}
                disabled={isConfirming}
                className="bg-emerald-600 text-white hover:bg-emerald-700"
              >
                {isConfirming ? (
                  "Saving..."
                ) : (
                  <>
                    <Check className="mr-1 size-4" />
                    Confirm & Save
                  </>
                )}
              </Button>

              {confirmResult && canCompute && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCompute}
                  disabled={isComputing}
                  className="border-slate-700 text-slate-200 hover:bg-slate-800"
                >
                  {isComputing ? (
                    "Computing..."
                  ) : (
                    <>
                      <Calculator className="mr-1 size-4" />
                      Compute Tax
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>

          {computeResult && (
            <div className="rounded-3xl border border-cyan-500/20 bg-cyan-500/5 p-4">
              <h3 className="mb-3 text-sm font-semibold text-cyan-200">Computation summary</h3>
              {computeResult.computation.error ? (
                <p className="text-sm text-red-300">{computeResult.computation.error}</p>
              ) : (
              <div className="space-y-2 text-sm text-slate-200">
                {computeResult.computation.old_regime_tax != null && (
                  <p>Old regime: Rs {computeResult.computation.old_regime_tax.toLocaleString("en-IN")}</p>
                )}
                {computeResult.computation.new_regime_tax != null && (
                  <p>New regime: Rs {computeResult.computation.new_regime_tax.toLocaleString("en-IN")}</p>
                )}
                {computeResult.computation.federal_tax != null && (
                  <p>Federal tax: ${computeResult.computation.federal_tax.toLocaleString("en-US")}</p>
                )}
                {computeResult.computation.recommended && (
                  <p className="font-semibold text-emerald-300">
                    Recommended: {computeResult.computation.recommended.toUpperCase()}
                  </p>
                )}
                {computeResult.computation.savings != null && (
                  <p className="text-emerald-300">
                    Estimated savings: Rs {computeResult.computation.savings.toLocaleString("en-IN")}
                  </p>
                )}
              </div>
              )}

              {!computeResult.computation.error && computeResult.computation.optimizations && computeResult.computation.optimizations.length > 0 && (
                <div className="mt-3 space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                    Optimization ideas
                  </p>
                  {computeResult.computation.optimizations.slice(0, 3).map((tip) => (
                    <p key={tip} className="text-sm text-slate-300">
                      {tip}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end gap-2 border-t border-slate-800 px-5 py-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={onDismiss}
          className="text-slate-400 hover:text-slate-200"
        >
          <X className="size-4 mr-1" />
          Close
        </Button>
      </div>
    </div>
  );
}
