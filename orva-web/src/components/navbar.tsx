"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { OrvaLogo } from "./orva-logo";
import {
  Search,
  CalendarClock,
  Home,
  MessageSquare,
  Phone,
  Users,
  Wrench,
  Bot,
  Crosshair,
  LogOut,
  Menu,
  X,
} from "lucide-react";

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  mobileNav?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Leads", icon: <Search size={18} />, mobileNav: true },
  {
    href: "/follow-ups",
    label: "Follow-Ups",
    icon: <CalendarClock size={18} />,
    mobileNav: true,
  },
  {
    href: "/lease-expiry",
    label: "Rentals",
    icon: <Home size={18} />,
  },
  {
    href: "/whatsapp",
    label: "WhatsApp",
    icon: <MessageSquare size={18} />,
    mobileNav: true,
  },
  {
    href: "/call-log",
    label: "Call Log",
    icon: <Phone size={18} />,
  },
  {
    href: "/contacts",
    label: "Contacts",
    icon: <Users size={18} />,
    mobileNav: true,
  },
  {
    href: "/chat",
    label: "HLM",
    icon: <Bot size={18} />,
    mobileNav: true,
  },
  {
    href: "/bayut",
    label: "Bayut",
    icon: <Home size={18} />,
  },
  {
    href: "/client-match",
    label: "Match",
    icon: <Crosshair size={18} />,
  },
];

const TOOL_ITEMS: NavItem[] = [
  { href: "/tools/pf-scraper", label: "PF Scraper", icon: <Wrench size={16} /> },
  { href: "/tools/reidin", label: "Reidin", icon: <Wrench size={16} /> },
  { href: "/matcher", label: "Matcher", icon: <Crosshair size={16} /> },
  { href: "/tools/health", label: "Health", icon: <Wrench size={16} /> },
];

export function Navbar() {
  const pathname = usePathname();
  const { authenticated, name, logout } = useAuth();
  const [toolsOpen, setToolsOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  if (!authenticated) return null;

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  const mobileItems = NAV_ITEMS.filter((i) => i.mobileNav);

  return (
    <>
      {/* Desktop navbar */}
      <nav className="hidden md:flex items-center gap-1 border-b border-border bg-card px-4 py-2">
        <Link href="/" className="mr-4">
          <OrvaLogo size="sm" />
        </Link>

        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              isActive(item.href)
                ? "bg-accent/15 text-accent"
                : "text-muted hover:bg-card-hover hover:text-foreground"
            }`}
          >
            {item.icon}
            {item.label}
          </Link>
        ))}

        {/* Tools dropdown */}
        <div className="relative">
          <button
            onClick={() => setToolsOpen(!toolsOpen)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              toolsOpen
                ? "bg-accent/15 text-accent"
                : "text-muted hover:bg-card-hover hover:text-foreground"
            }`}
          >
            <Wrench size={18} />
            Tools
          </button>
          {toolsOpen && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setToolsOpen(false)}
              />
              <div className="absolute right-0 top-full z-50 mt-1 w-44 rounded-lg border border-border bg-card py-1 shadow-lg">
                {TOOL_ITEMS.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setToolsOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-sm text-muted hover:bg-card-hover hover:text-foreground"
                  >
                    {item.icon}
                    {item.label}
                  </Link>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm text-muted">{name}</span>
          <button
            onClick={logout}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-muted hover:bg-card-hover hover:text-danger"
          >
            <LogOut size={16} />
          </button>
        </div>
      </nav>

      {/* Mobile top bar */}
      <nav className="flex md:hidden items-center justify-between border-b border-border bg-card px-4 py-2">
        <Link href="/">
          <OrvaLogo size="sm" />
        </Link>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="rounded-lg p-2 text-muted hover:bg-card-hover"
        >
          {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </nav>

      {/* Mobile slide-out menu */}
      {mobileMenuOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/50 md:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="fixed right-0 top-0 z-50 h-full w-64 border-l border-border bg-card p-4 md:hidden">
            <div className="mb-4 flex items-center justify-between">
              <span className="text-sm font-medium text-foreground">Menu</span>
              <button
                onClick={() => setMobileMenuOpen(false)}
                className="rounded-lg p-1 text-muted hover:text-foreground"
              >
                <X size={20} />
              </button>
            </div>
            <div className="flex flex-col gap-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium ${
                    isActive(item.href)
                      ? "bg-accent/15 text-accent"
                      : "text-muted hover:bg-card-hover hover:text-foreground"
                  }`}
                >
                  {item.icon}
                  {item.label}
                </Link>
              ))}
              <div className="my-2 border-t border-border" />
              <span className="px-3 py-1 text-xs font-medium uppercase tracking-wider text-muted">
                Tools
              </span>
              {TOOL_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm text-muted hover:bg-card-hover hover:text-foreground"
                >
                  {item.icon}
                  {item.label}
                </Link>
              ))}
              <div className="my-2 border-t border-border" />
              <button
                onClick={() => {
                  logout();
                  setMobileMenuOpen(false);
                }}
                className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm text-danger hover:bg-card-hover"
              >
                <LogOut size={16} />
                Sign out
              </button>
            </div>
          </div>
        </>
      )}

      {/* Mobile bottom navigation */}
      <nav className="fixed bottom-0 left-0 right-0 z-30 flex md:hidden items-center justify-around border-t border-border bg-card py-2 safe-bottom">
        {mobileItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`relative flex flex-col items-center justify-center gap-0.5 min-h-[48px] min-w-[48px] px-1 py-1.5 active:scale-95 transition-transform duration-100 ${
              isActive(item.href) ? "text-accent" : "text-muted"
            }`}
          >
            {isActive(item.href) && (
              <span className="absolute top-0 left-1/4 right-1/4 h-0.5 rounded-full bg-accent" />
            )}
            {item.icon}
            <span className="text-[10px]">{item.label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
