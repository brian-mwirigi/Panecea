"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  /** Enable hover lift + accent glow. */
  interactive?: boolean;
  /** Stagger index for entrance animation. */
  delay?: number;
}

/** Frosted-glass surface used as the base for every dashboard panel. */
export function GlassCard({
  children,
  className = "",
  interactive = false,
  delay = 0,
}: GlassCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      className={`glass ${interactive ? "glass-hover" : ""} rounded-2xl ${className}`}
    >
      {children}
    </motion.div>
  );
}

interface PanelHeaderProps {
  title: string;
  icon?: ReactNode;
  subtitle?: string;
  action?: ReactNode;
}

/** Consistent header row for panels. */
export function PanelHeader({ title, icon, subtitle, action }: PanelHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3">
      <div className="flex items-center gap-3">
        {icon && (
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-white/5 text-accent ring-1 ring-white/10">
            {icon}
          </div>
        )}
        <div>
          <h2 className="text-sm font-semibold tracking-wide text-white/90">{title}</h2>
          {subtitle && <p className="text-xs text-white/40">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}
