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
