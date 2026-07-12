import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { cn } from "../lib/utils";

export interface NavItem {
  label: string;
  to: string;
}

export interface SpotlightNavbarProps {
  items: NavItem[];
  className?: string;
}

export function SpotlightNavbar({
  items,
  className,
}: SpotlightNavbarProps) {
  const location = useLocation();
  const navRef = useRef<HTMLDivElement>(null);
  
  // Find active index based on route location
  const activeIndex = items.findIndex(item => item.to === location.pathname);
  const resolvedActiveIndex = activeIndex !== -1 ? activeIndex : 0;

  const [hoverX, setHoverX] = useState<number | null>(null);

  useEffect(() => {
    if (!navRef.current) return;
    const nav = navRef.current;

    const handleMouseMove = (e: MouseEvent) => {
      const rect = nav.getBoundingClientRect();
      const x = e.clientX - rect.left;
      setHoverX(x);
      nav.style.setProperty("--spotlight-x", `${x}px`);
    };

    const handleMouseLeave = () => {
      setHoverX(null);
    };

    nav.addEventListener("mousemove", handleMouseMove);
    nav.addEventListener("mouseleave", handleMouseLeave);

    return () => {
      nav.removeEventListener("mousemove", handleMouseMove);
      nav.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, []);

  return (
    <div className={cn("relative flex items-center justify-center", className)}>
      <nav
        ref={navRef}
        className={cn(
          "spotlight-nav relative h-10 rounded-full transition-all duration-300 overflow-hidden flex items-center p-1"
        )}
      >
        {/* Content */}
        <ul className="relative flex items-center h-full gap-1 z-[10]">
          {items.map((item, idx) => {
            const isActive = resolvedActiveIndex === idx;
            return (
              <li key={idx} className="relative h-full flex items-center justify-center">
                <Link
                  to={item.to}
                  data-index={idx}
                  className={cn(
                    "relative px-4 py-1.5 text-sm font-semibold transition-colors duration-200 rounded-full flex items-center justify-center",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/30",
                    isActive
                      ? "text-brand-600 font-bold"
                      : "text-slate-600 hover:text-slate-900"
                  )}
                >
                  {/* Sliding Pill Background */}
                  {isActive && (
                    <motion.div
                      layoutId="active-nav-pill"
                      className="absolute inset-0 bg-brand-50 rounded-full -z-10 border border-brand-100/30"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>

        {/* The Moving Spotlight (Follows Mouse) */}
        <div
          className="pointer-events-none absolute inset-0 z-[1] opacity-0 transition-opacity duration-300"
          style={{
            opacity: hoverX !== null ? 1 : 0,
            background: `
              radial-gradient(
                80px circle at var(--spotlight-x) 50%, 
                rgba(37, 99, 235, 0.06) 0%, 
                transparent 100%
              )
            `
          }}
        />
      </nav>
    </div>
  );
}
