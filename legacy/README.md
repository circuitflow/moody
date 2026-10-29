# Legacy: the 2007 Moody thesis

Moody began as the *Mood Player*, the software behind Owen Meyers' MIT Media Lab S.M. thesis,
*A Mood-Based Music Classification and Exploration System* (June 2007). The original code is
archived unchanged at [circuitflow/moody-2007](https://github.com/circuitflow/moody-2007)
(commit `3b58348`). It targets Python 2.4 on Mac OS X 10.4 and depends on services that no longer
exist: The Echo Nest analyzer and LyricWiki.

This folder keeps the parts that are still useful, the model and its data, so the 2026 rewrite can
use the 2007 system as a baseline.

| What | Where |
|---|---|
| Decision tree, octants, feature normalizations, k-NN | [`backend/src/moody/legacy/thesis2007.py`](../backend/src/moody/legacy/thesis2007.py) (typed Python 3 port) |
| 372-song training set | [`data/thesis2007_training.csv`](data/thesis2007_training.csv) |
| Converter from the original pickles | [`convert.py`](convert.py) |
| Numbers in "Known issues" below | [`known_issues.py`](known_issues.py) (run from `backend/`: `uv run python ../legacy/known_issues.py`) |

Not carried over: the CLAM, Echo Nest and Qt binaries, ConceptNet/MontyLingua, the PyGTK UI, local
file paths and lyric text.

## The 2007 model

Five features, each scaled to 0–100, are thresholded into a 32-leaf decision tree. Each leaf is a
Hevner adjective assigned to one of the eight octants of Russell's circumplex: Pleasure, Excitement,
Arousal, Distress, Displeasure, Depression, Sleepiness and Relaxation, counter-clockwise from
positive valence in 45° steps.

| Feature | 2007 source | Scaling | Threshold (≥ → first label) |
|---|---|---|---|
| mode | CLAM ChordExtractor: weighted share of major chords among the top roots | 0–100 | 50: major / minor |
| harmony | CLAM: share of simple (major, minor, fifth) chords | 0–100 | 75: simple / complex |
| tempo | Echo Nest tempo | 40–200 BPM → 0–100 | 40: fast / slow |
| rhythm | Echo Nest tempo confidence ×30, (1 − beat variance) ×50, tatum confidence ×15, time-signature stability ×5, averaged | 10–25 → 0–100 | 65: regular / irregular |
| loudness | Echo Nest loudness | 20–80 → 0–100 | 50: loud / soft |

A k-NN classifier (k = 1…9) over the same five features ran alongside the tree.

## The training set: what the labels are

`thesis2007_training.csv` has 372 songs with the following columns:
- ID3 artist, album and genre
- the AllMusic (AMG) mood tag
- the 2007 octant and Hevner adjective
- the five features
- the top octant from the lyric-affect analysis (ConceptNet)

**The `octant_2007` and `hevner_2007` columns are the decision tree's own outputs, not independent
human labels.** The test suite checks that the port reproduces all 372 of them. The 2007 k-NN was
trained on these tree labels, so its accuracy measures how well it imitates the tree: 64.8%
leave-one-out at k = 5 (241/372). The only independent labels are the AMG mood tags. They are
free-form editorial words, and only 26 of 372 map unambiguously onto an octant through the thesis's
own octant lexicon.

The 2007-vs-2026 comparison (M4) therefore works like this:
- 2007 features are re-derived from audio with Essentia, and the tree is run on them.
- The 2007 verdicts are compared against the DEAM valence/arousal ground truth, alongside the 2026 models.
- On this 372-song set, 2007 octants and AMG tags are compared with the 2026 model outputs.
- 2007 verdicts are reported together with their stability under feature noise (issue 2 below), and the leaves from issues 3 and 4 are flagged.

## Known issues in the 2007 system

Found while reviewing the archive for the rewrite (2026-10). The port in `thesis2007.py` stays faithful to
the original, issues included, so that the 2007 baseline is what the thesis actually ran. Line numbers
refer to the archive at commit `3b58348`.

| # | Issue | Evidence | Effect |
|---|---|---|---|
| 1 | The training labels are the tree's own outputs | the port reproduces 372/372 | The k-NN learns to imitate the tree (64.8% leave-one-out at k = 5); there is no independent ground truth in the set apart from the AMG tags. |
| 2 | Thresholds sit at the feature medians | mode: median 52.4 vs threshold 50, with 41% of songs within ±5; harmony: median 76.1 vs 75, with 50% within ±5 | Verdicts are fragile: feature noise of ±1 / ±3 / ±5 points (0–100 scale) changes 10% / 28% / 41% of octants. |
| 3 | The "vigorous" leaf (minor, complex, fast, irregular, loud) maps to Depression, a low-arousal octant | `DecisionTree.py:148`; 28 songs, e.g. "We Will Rock You", "Deutschland (Has Gotta Die!)" | High-energy songs land in a low-energy octant. |
| 4 | Minor-mode "humorous" and "playful" map to Pleasure | `DecisionTree.py:117,120`; 22 songs | This contradicts Hevner's finding that minor mode reads as sad or dreamy. |
| 5 | The Hevner/Schubert weights are listed but not applied | the 8×5 weight matrix only appears in a string under `# incorporate hevner's weighting here` (`DecisionTree.py:6-19`); the archive README describes the features as "weighted per mood using Hevner's findings" | The tree uses fixed thresholds only. |
| 6 | Copy-paste slips in `Analyzer.py` | `getHarmony` reads the stored `songMode` tag (line 103); `getTempo` reads `songHarmony` (line 117); `getMode` tallies `minor` but returns the `major` tally alone (line 64); the harmony split leaves Major7 out of both "simple" and "complex" (lines 85–86) | Mostly harmless: a stored tag value is used only when it exactly equals the newly computed one. If those tags are empty, the code raises an error (in this data they are all `"0"`). Whether the `major` tally is a share depends on CLAM's undocumented scaling. |
| 7 | Lyric affect and audio verdict rarely agree | the lyric octant matches the audio octant for 33/372 songs (8.9%) | Below the 12.5% chance level. Instrumentals also have a lyric octant (e.g. Aphex Twin), so the lyric signal includes fallback values. |

None of these affect the 2026 pipeline, which uses no 2007 code, labels or features for its own valence/arousal.
They matter for the M4 2007-vs-2026 comparison and for how the thesis results are described.
