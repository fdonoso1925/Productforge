import { z } from "zod";
import { FORMATS } from "@/lib/types";

// Validación de lo que el usuario escribe (mismos límites que el backend).

export const nicheSchema = z.string().trim().min(2).max(120);

// Límites holgados en todo lo que también genera la IA: deben aceptar sus respuestas
// válidas (el backend no limita estos campos) y solo frenar textos absurdos.
export const problemSchema = z.object({
  title: z.string().trim().min(5).max(500),
  audience: z.string().trim().min(2).max(1000),
  pain: z.string().trim().min(2).max(1000),
  promised_result: z.string().trim().min(2).max(1000),
  timeframe: z.string().trim().min(1).max(400),
  why_pay: z.string().trim().max(1000),
  urgency: z.number().int().min(1).max(5),
});

const itemSchema = z.object({
  role: z.enum(["main", "order_bump", "bonus"]),
  format: z.enum(FORMATS),
  title: z.string().trim().min(2).max(300),
  promise: z.string().trim().min(2).max(800),
  objection_addressed: z.string().trim().max(500).nullable(),
  table_of_contents: z.array(z.string().trim().min(1).max(500)).min(1).max(60),
  estimated_pages: z.number().int().min(1).max(60),
  related_items: z.array(z.string()),
});

export const outlineSchema = z.object({
  product_name: z.string().trim().min(2).max(300),
  main: itemSchema,
  order_bumps: z.array(itemSchema).min(3),
  bonuses: z.array(itemSchema).min(2),
});
