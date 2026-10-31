import { describe, expect, it } from "vitest";
import { cosine, decodeEmbeddings, encodeEmbeddings } from "./embeddings";

describe("style vectors", () => {
  it("round-trips base64 little-endian float32", () => {
    const rows = [
      [1, 0, 0],
      [0.6, 0.8, 0],
      [0, 0, 0],
    ];
    const v = decodeEmbeddings(encodeEmbeddings([7, 9, 11], rows));
    expect(v.dims).toBe(3);
    expect(v.rowOf.get(9)).toBe(1);
    expect(Array.from(v.data)).toEqual(rows.flat().map((x) => Math.fround(x)));
    expect(cosine(v, 0, 1)).toBeCloseTo(0.6);
    expect(cosine(v, 0, 2)).toBe(0);
  });

  it("decodes the API's empty payload", () => {
    const v = decodeEmbeddings({ id: [], dims: 0, vectors: "" });
    expect(v.data.length).toBe(0);
  });
});
