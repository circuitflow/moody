export function fieldLabel(field: string): string {
  if (field === "bpm") return "Tempo (BPM)";
  if (field === "loudness") return "Loudness (LUFS)";
  return `“${field.replace("tag:", "")}” tag probability`;
}
