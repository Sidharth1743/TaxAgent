"use client";

import { useState } from "react";
import { Settings } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

const VOICE_OPTIONS = ["Aoede", "Charon", "Fenrir", "Kore", "Puck"] as const;

interface SettingsDialogProps {
  voice: string;
  onVoiceChange: (v: string) => void;
  modality: string[];
  onModalityChange: (m: string[]) => void;
}

export function SettingsDialog({
  voice,
  onVoiceChange,
  modality,
  onModalityChange,
}: SettingsDialogProps) {
  const [open, setOpen] = useState(false);
  const isTextAssist = modality.length === 1 && modality[0] === "TEXT";

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-slate-400 hover:text-slate-200 hover:bg-slate-800"
          />
        }
      >
        <Settings className="size-5" />
        <span className="sr-only">Settings</span>
      </DialogTrigger>
      <DialogContent className="bg-slate-950 border border-slate-800 text-slate-100">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold text-slate-50">
            Settings
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-6 py-2">
          {/* Voice selection */}
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-slate-300">Voice</label>
            <Select value={voice} onValueChange={(v) => { if (v) onVoiceChange(v); }}>
              <SelectTrigger className="w-full bg-slate-900 border-slate-700 text-slate-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-900 border-slate-700">
                {VOICE_OPTIONS.map((v) => (
                  <SelectItem key={v} value={v} className="text-slate-200 focus:bg-slate-800">
                    {v}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Interaction mode toggle */}
          <div className="flex items-center justify-between">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-slate-300">
                Keyboard Assist
              </label>
              <span className="text-xs text-slate-500">
                {isTextAssist
                  ? "Connect without microphone and chat by text"
                  : "Use microphone, camera, and live voice replies"}
              </span>
            </div>
            <Switch
              checked={isTextAssist}
              onCheckedChange={(checked: boolean) => {
                onModalityChange(checked ? ["TEXT"] : ["AUDIO"]);
              }}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
