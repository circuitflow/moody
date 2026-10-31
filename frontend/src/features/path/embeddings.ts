/** Decoding of the compact style vectors served by `/api/embeddings` (and `embeddings.json`). */
import type { Embeddings } from "../../api/types";

export interface StyleVectors {
  dims: number;
  /** Row-major, `ids.length` rows of `dims` values; each row is unit length (or all zeros). */
  data: Float32Array;
  rowOf: Map<number, number>;
}

export function decodeEmbeddings(e: Embeddings): StyleVectors {
  const binary = atob(e.vectors);
  const view = new DataView(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i++) view.setUint8(i, binary.charCodeAt(i));
  const data = new Float32Array(e.id.length * e.dims);
  for (let i = 0; i < data.length; i++) data[i] = view.getFloat32(i * 4, true); // little-endian
  return { dims: e.dims, data, rowOf: new Map(e.id.map((id, row) => [id, row])) };
}

export function encodeEmbeddings(ids: number[], rows: number[][]): Embeddings {
  const dims = rows[0]?.length ?? 0;
  const view = new DataView(new ArrayBuffer(ids.length * dims * 4));
  rows.flat().forEach((x, i) => view.setFloat32(i * 4, x, true));
  let binary = "";
  for (let i = 0; i < view.byteLength; i++) binary += String.fromCharCode(view.getUint8(i));
  return { id: ids, dims, vectors: btoa(binary) };
}

/** Cosine similarity of two tracks (rows are unit length); 0 when either has no vector. */
export function cosine(v: StyleVectors, rowA: number, rowB: number): number {
  let dot = 0;
  const a = rowA * v.dims;
  const b = rowB * v.dims;
  for (let k = 0; k < v.dims; k++) dot += v.data[a + k]! * v.data[b + k]!;
  return dot;
}
