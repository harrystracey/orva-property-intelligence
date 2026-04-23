"use client";

import {
  Search,
  MessageSquare,
  Mail,
  Crosshair,
  CalendarClock,
  ChevronDown,
} from "lucide-react";
import { LoginForm } from "./login-form";

const serif = "Georgia, 'Times New Roman', serif";

function HeroSection() {
  return (
    <section className="relative flex min-h-[100dvh] flex-col items-center justify-center px-6">
      {/* Wordmark -- responsive sizing so the hero doesn't eat the viewport
          on 375px phones where 3rem previously clipped. */}
      <h1
        className="text-4xl sm:text-5xl md:text-6xl text-foreground"
        style={{
          fontFamily: serif,
          fontWeight: 300,
          letterSpacing: "0.35em",
        }}
      >
        ORVA
      </h1>

      {/* Tagline */}
      <p
        className="mt-3 text-center text-muted"
        style={{
          fontFamily: serif,
          fontWeight: 400,
          fontSize: "0.8rem",
          letterSpacing: "0.2em",
        }}
      >
        PROPERTY INTELLIGENCE
      </p>

      {/* Gold line */}
      <div className="mt-10 h-px w-20 bg-accent/40" />

      {/* Subtitle */}
      <p
        className="mt-10 text-center text-muted/60"
        style={{
          fontSize: "0.8rem",
          letterSpacing: "0.15em",
        }}
      >
        PALM JUMEIRAH EXCLUSIVE
      </p>

      {/* Scroll indicator */}
      <button
        onClick={() =>
          document
            .getElementById("value")
            ?.scrollIntoView({ behavior: "smooth" })
        }
        className="absolute bottom-10 animate-bounce text-accent/40"
      >
        <ChevronDown size={24} />
      </button>
    </section>
  );
}

const VALUE_PROPS = [
  {
    icon: <Search size={28} strokeWidth={1} />,
    title: "Owner Intelligence",
    description:
      "Search 78,975 verified Palm Jumeirah owner records. Filter by building, unit, portfolio size, and contact completeness.",
    tag: "78,975 RECORDS",
  },
  {
    icon: <MessageSquare size={28} strokeWidth={1} />,
    title: "HLM Intelligence",
    description:
      "Query the entire database in plain English. Ask about owners, leases, prices, and buildings without filters or exports.",
    tag: "AI-NATIVE",
  },
  {
    icon: <Mail size={28} strokeWidth={1} />,
    title: "WhatsApp Campaigns",
    description:
      "Seven targeting modes with dual-account delivery. Preview, launch, and monitor outreach campaigns in real time.",
    tag: "DUAL ACCOUNT",
  },
];

function ValueSection() {
  return (
    <section id="value" className="px-6 py-24">
      <div className="mx-auto max-w-5xl">
        <div className="grid gap-6 md:grid-cols-3">
          {VALUE_PROPS.map((prop) => (
            <div
              key={prop.title}
              className="group flex flex-col rounded-xl border border-border bg-card p-8 transition-colors hover:border-accent/30"
            >
              <div className="text-accent/70">{prop.icon}</div>
              <h3
                className="mt-6 text-foreground"
                style={{
                  fontFamily: serif,
                  fontSize: "1.25rem",
                  fontWeight: 400,
                }}
              >
                {prop.title}
              </h3>
              <p className="mt-3 flex-1 text-sm leading-relaxed text-muted">
                {prop.description}
              </p>
              <div className="mt-6 border-t border-border pt-4">
                <span
                  className="text-accent"
                  style={{ fontSize: "0.7rem", letterSpacing: "0.15em" }}
                >
                  {prop.tag}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const FEATURES = [
  { icon: <Search size={16} />, label: "Lead Search" },
  { icon: <MessageSquare size={16} />, label: "WhatsApp Campaigns" },
  { icon: <Crosshair size={16} />, label: "Client Matching" },
  { icon: <CalendarClock size={16} />, label: "Lease Tracking" },
];

function FeatureStrip() {
  return (
    <section className="border-y border-border px-6 py-10">
      <div className="mx-auto max-w-5xl">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {FEATURES.map((f) => (
            <div
              key={f.label}
              className="flex items-center gap-2.5 text-muted"
            >
              <span className="text-accent/50">{f.icon}</span>
              <span
                style={{ fontSize: "0.7rem", letterSpacing: "0.1em" }}
              >
                {f.label.toUpperCase()}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const STATS = [
  { value: "189", label: "BUILDINGS" },
  { value: "36,500+", label: "DLD TRANSACTIONS" },
  { value: "78,556", label: "OWNER LEADS" },
  { value: "100%", label: "PALM JUMEIRAH" },
];

function StatsBar() {
  return (
    <section className="px-6 py-20">
      <div className="mx-auto max-w-5xl">
        <div className="grid grid-cols-2 gap-10 md:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="text-center">
              <p
                className="text-foreground"
                style={{
                  fontFamily: serif,
                  fontSize: "2rem",
                  fontWeight: 300,
                }}
              >
                {s.value}
              </p>
              <p
                className="mt-2 text-muted"
                style={{ fontSize: "0.65rem", letterSpacing: "0.15em" }}
              >
                {s.label}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SignInSection() {
  return (
    <section className="px-6 pb-20 pt-8">
      <div className="mx-auto max-w-sm">
        {/* Gold line */}
        <div className="mb-10 h-px w-full bg-border" />

        <p
          className="mb-6 text-center text-muted"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.25em",
          }}
        >
          SIGN IN
        </p>

        <LoginForm embedded />
      </div>
    </section>
  );
}

export function LandingPage() {
  return (
    <div className="flex flex-col">
      <HeroSection />
      <ValueSection />
      <FeatureStrip />
      <StatsBar />
      <SignInSection />
    </div>
  );
}
