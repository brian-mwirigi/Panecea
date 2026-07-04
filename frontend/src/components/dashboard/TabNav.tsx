"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";

export interface TabDef {
  id: string;
  label: string;
  icon: LucideIcon;
  hint?: string;
}

interface TabNavProps {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
}

/** Segmented, glassy navigation between the main dashboard views. */
export function TabNav({ tabs, active, onChange }: TabNavProps) {
  return (
    <div className="glass flex w-full gap-1 rounded-2xl p-1.5 sm:w-auto">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`relative flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors sm:flex-none ${
              isActive ? "text-white" : "text-white/45 hover:text-white/70"
            }`}
          >
            {isActive && (
              <motion.span
                layoutId="tab-active"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
                className="absolute inset-0 rounded-xl bg-white/8 ring-1 ring-white/10"
              />
            )}
            <Icon className="relative h-4 w-4" />
            <span className="relative">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
