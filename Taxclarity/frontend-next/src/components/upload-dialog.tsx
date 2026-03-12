"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { ExtractedDocument } from "@/types";

const GRAPH_API_URL =
  process.env.NEXT_PUBLIC_GRAPH_API_URL ??
  (typeof window !== "undefined" ? window.location.origin : "http://localhost:8006");

interface UploadDialogProps {
  onDocumentExtracted: (doc: ExtractedDocument) => void;
}

export function UploadDialog({ onDocumentExtracted }: UploadDialogProps) {
  const [open, setOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setError("Please select a file first.");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${GRAPH_API_URL}/api/documents/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errBody = await response.text();
        throw new Error(errBody || `Upload failed (${response.status})`);
      }

      const doc: ExtractedDocument = await response.json();
      onDocumentExtracted(doc);
      setOpen(false);

      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        setOpen(isOpen);
        if (!isOpen) {
          setError(null);
          setIsUploading(false);
        }
      }}
    >
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            title="Upload a document, or show it on camera during voice session"
          />
        }
      >
        <Upload className="size-5" />
        <span className="sr-only">Upload Document</span>
      </DialogTrigger>
      <DialogContent className="bg-slate-950 border border-slate-800 text-slate-100">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold text-slate-50">
            Upload Tax Document
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <p className="text-sm text-slate-400">
            Select a PDF or image of a tax form (W-2, 1099, Form 16, etc.)
          </p>

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png"
            className="block w-full text-sm text-slate-300 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer"
          />

          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}

          <Button
            onClick={handleSubmit}
            disabled={isUploading}
            className="bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            {isUploading ? "Extracting..." : "Upload & Extract"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
