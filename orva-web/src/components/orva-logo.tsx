"use client";

export function OrvaLogo({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const dims = { sm: 28, md: 36, lg: 48 }[size];
  const fontSize = { sm: "text-sm", md: "text-lg", lg: "text-2xl" }[size];
  const subSize = { sm: "text-[8px]", md: "text-[9px]", lg: "text-xs" }[size];

  return (
    <div className="flex items-center gap-2">
      <div
        className="flex items-center justify-center rounded-lg font-bold text-white"
        style={{
          width: dims,
          height: dims,
          background: "linear-gradient(135deg, #10b981, #059669)",
          fontSize: dims * 0.5,
        }}
      >
        O
      </div>
      <div className="flex flex-col leading-none">
        <span className={`${fontSize} font-bold tracking-wider text-foreground`}>
          ORVA
        </span>
        <span
          className={`${subSize} font-medium tracking-[0.2em] text-muted uppercase`}
        >
          Property Intelligence
        </span>
      </div>
    </div>
  );
}
