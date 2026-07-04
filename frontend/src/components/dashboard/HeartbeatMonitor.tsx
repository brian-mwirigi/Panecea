"use client";

import { useMemo, useState } from "react";
import { HeartPulse, ChevronDown } from "lucide-react";
import { GlassCard, PanelHeader } from "./GlassCard";
import { useHeartbeat } from "@/hooks/useHeartbeat";
import { config } from "@/lib/config";
import type { Device } from "@/lib/types";

interface HeartbeatMonitorProps {
  devices: Device[];
}

export function HeartbeatMonitor({ devices }: HeartbeatMonitorProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const active = devices.find((d) => d.id === selectedId) ?? devices[0];
  const bpm = active?.bpm ?? 72;

  const tone =
    bpm > 120 ? "danger" : bpm > 105 ? "warn" : "good";

  return (
    <GlassCard delay={0.1} className="flex h-full flex-col overflow-hidden">
      <PanelHeader
        title="Device Heartbeat Telemetry"
        subtitle={config.useMock ? "Live vitals · simulated feed" : "Live device-twin telemetry"}
        icon={<HeartPulse className="h-4.5 w-4.5" />}
        action={
          devices.length > 0 && (
            <DeviceSelect
              devices={devices}
              value={active?.id ?? ""}
              onChange={setSelectedId}
            />
          )
        }
      />
      <div className="relative flex-1 px-3 pb-3">
        <div className="grid-overlay relative h-full min-h-44 overflow-hidden rounded-xl bg-black/30 ring-1 ring-white/5">
          <Ecg bpm={bpm} tone={tone} />
          <div className="pointer-events-none absolute left-4 top-3">
            <div className="text-[10px] uppercase tracking-widest text-white/40">
              {active?.model ?? "—"}
            </div>
            <div className="text-[10px] text-white/30">{active?.vpc_id ?? ""}</div>
          </div>
          <div className="pointer-events-none absolute bottom-3 right-4 flex items-end gap-1">
            <span
              className={`font-mono text-3xl font-bold tabular-nums ${
                tone === "danger"
                  ? "text-danger"
                  : tone === "warn"
                    ? "text-warn"
                    : "text-accent-2"
              }`}
            >
              {bpm}
            </span>
            <span className="pb-1 text-xs text-white/40">BPM</span>
          </div>
        </div>
      </div>
    </GlassCard>
  );
}

function Ecg({ bpm, tone }: { bpm: number; tone: string }) {
  const samples = useHeartbeat({ bpm, window: 200, intervalMs: 40 });
  const stroke =
    tone === "danger" ? "#fb7185" : tone === "warn" ? "#fbbf24" : "#34d399";

  const points = useMemo(() => {
    const w = 1000;
    const h = 100;
    const n = samples.length;
    return samples
      .map((s, i) => {
        const x = (i / (n - 1)) * w;
        const y = h / 2 - s.value * (h * 0.42);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [samples]);

  return (
    <svg
      viewBox="0 0 1000 100"
      preserveAspectRatio="none"
      className="h-full w-full"
    >
      <defs>
        <linearGradient id="ecgFade" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={stroke} stopOpacity="0" />
          <stop offset="20%" stopColor={stroke} stopOpacity="0.35" />
          <stop offset="100%" stopColor={stroke} stopOpacity="1" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2.4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <polyline
        points={points}
        fill="none"
        stroke="url(#ecgFade)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        filter="url(#glow)"
      />
    </svg>
  );
}

function DeviceSelect({
  devices,
  value,
  onChange,
}: {
  devices: Device[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none rounded-lg bg-white/5 py-1.5 pl-3 pr-8 text-xs text-white/70 ring-1 ring-white/10 outline-none transition hover:bg-white/10 focus:ring-accent/40"
      >
        {devices.map((d) => (
          <option key={d.id} value={d.id} className="bg-[#0b1020] text-white">
            {d.model}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/40" />
    </div>
  );
}
