"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

const DISARM_MS = 4000;

/**
 * Botón de dos pasos para acciones que gastan IA: el primer clic lo "arma" (cambia el texto) y
 * el segundo ejecuta. Se desarma solo tras unos segundos. Evita los diálogos del navegador.
 */
export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  disabled,
  size = "sm",
  icon,
}: {
  label: string;
  confirmLabel: string;
  onConfirm: () => void;
  disabled?: boolean;
  size?: "sm" | "default" | "lg";
  icon?: React.ReactNode;
}) {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!armed) return;
    const timer = setTimeout(() => setArmed(false), DISARM_MS);
    return () => clearTimeout(timer);
  }, [armed]);

  return (
    <Button
      variant={armed ? "default" : "outline"}
      size={size}
      disabled={disabled}
      onClick={() => {
        if (!armed) return setArmed(true);
        setArmed(false);
        onConfirm();
      }}
      onBlur={() => setArmed(false)}
    >
      {icon}
      {armed ? confirmLabel : label}
    </Button>
  );
}
