"use client";

interface DisclaimerModalProps {
  acknowledged: boolean;
  onAcknowledge: () => void;
}

export function DisclaimerModal({ acknowledged, onAcknowledge }: DisclaimerModalProps) {
  if (acknowledged) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      aria-modal="true"
      role="dialog"
      aria-labelledby="disclaimer-title"
    >
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-6 w-full max-w-sm mx-4 shadow-2xl">
        <h2
          id="disclaimer-title"
          className="text-lg font-semibold text-slate-50 mb-3"
        >
          Important Notice
        </h2>
        <p className="text-slate-400 leading-relaxed text-sm mb-6">
          TaxClarity provides informational guidance only. This is not legal
          or financial advice. Consult a qualified tax professional for your
          specific situation.
        </p>
        <button
          onClick={onAcknowledge}
          className="w-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-medium py-2 px-4 rounded-lg transition-colors cursor-pointer"
        >
          I Understand
        </button>
      </div>
    </div>
  );
}
