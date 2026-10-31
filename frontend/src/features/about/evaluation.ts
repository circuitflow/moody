/** Typed access to the evaluation summary written by `eval/render.py`. */
import raw from "./evaluation.json";

export interface OctantStats {
  n: number;
  exact: number;
  within_one: number;
  mean_angle_error_deg: number;
}

export interface TagScore {
  tag: string;
  positives: number;
  prevalence: number;
  roc_auc: number;
  pr_auc: number;
}

export interface Evaluation {
  deam: {
    n: number;
    valence_r: number;
    arousal_r: number;
    contrast_r: number;
    predicted_va_corr: number;
    rated_va_corr: number;
    loudness_vs_v_minus_a: { model: number | null; listeners: number | null };
    octants: {
      clear: { "2026_head": OctantStats; "2007_tree": OctantStats; chance_exact: number };
      clear_radius: number;
      note: string;
    } | null;
  } | null;
  tags: {
    tracks: number;
    tags_evaluated: number;
    macro_roc_auc: number;
    macro_pr_auc: number;
    best: TagScore[];
    worst: TagScore[];
  } | null;
}

export const evaluation = raw as unknown as Evaluation;
