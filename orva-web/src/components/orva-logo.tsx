"use client";

export function OrvaLogo({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const fontSize = { sm: "text-sm", md: "text-lg", lg: "text-2xl" }[size];
  const subSize = { sm: "text-[7px]", md: "text-[8px]", lg: "text-[10px]" }[size];

  return (
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
        className={`${subSize} text-muted`}
        style={{
          letterSpacing: "0.2em",
          fontWeight: 400,
        }}
      >
        PROPERTY INTELLIGENCE
      </span>
    </div>
  );
}
