"use client";

export function OrvaLogo({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const dims = { sm: 28, md: 36, lg: 48 }[size];
  const fontSize = { sm: "text-sm", md: "text-lg", lg: "text-2xl" }[size];
  const subSize = { sm: "text-[7px]", md: "text-[8px]", lg: "text-[10px]" }[size];

  return (
    <div className="flex items-center gap-2.5">
      <div
        className="flex items-center justify-center rounded-lg text-white"
        style={{
          width: dims,
          height: dims,
          background: "linear-gradient(145deg, #10b981 0%, #047857 60%, #064e3b 100%)",
          fontSize: dims * 0.45,
          fontWeight: 300,
          fontFamily: "Georgia, 'Times New Roman', serif",
          letterSpacing: "0.02em",
          boxShadow: "0 1px 3px rgba(16, 185, 129, 0.15)",
        }}
      >
        O
      </div>
      <div className="flex flex-col leading-none">
        <span
          className={`${fontSize} text-foreground`}
          style={{
            fontWeight: 300,
            letterSpacing: "0.25em",
            fontFamily: "Georgia, 'Times New Roman', serif",
          }}
        >
          ORVA
        </span>
        <span
          className={`${subSize} text-muted/60`}
          style={{
            letterSpacing: "0.3em",
            fontWeight: 400,
          }}
        >
          PROPERTY INTELLIGENCE
        </span>
      </div>
    </div>
  );
}
