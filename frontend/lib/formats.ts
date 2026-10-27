import {
  BookOpen,
  CalendarDays,
  Copy,
  FilePen,
  FileText,
  ListChecks,
  type LucideIcon,
  Map as MapIcon,
  Network,
  Printer,
  Share2,
  Sheet,
} from "lucide-react";
import type { Format } from "@/lib/types";

export const FORMAT_ICONS: Record<Format, LucideIcon> = {
  pdf_guide: FileText,
  epub: BookOpen,
  mind_map: Network,
  concept_map: Share2,
  sheet: Sheet,
  checklist: ListChecks,
  blueprint: MapIcon,
  editable_template: FilePen,
  planner: CalendarDays,
  swipe_file: Copy,
  printable: Printer,
};
