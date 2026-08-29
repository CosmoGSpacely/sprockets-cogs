# Archived Modelfiles

Retired 2026-08-29, Stage 142 slice 0. Kept, not deleted: these are the only
record of how the Stage 138 roster models were built, and Stage 140 will need
them if it reopens the model comparison.

## What happened

The project ran two tags of the same weights - `gemma4:12b-16k-cosmo` and
`gemma4:12b-32k-cosmo` - differing only in `num_ctx`. Measurement during
Stage 142 slice 0 established two things:

1. **The two tags are indistinguishable on this workload.** Measured in
   isolation, one model resident at a time, six captures each after a
   discarded warmup:

   | tag | prefill/capture | decode/capture | VRAM |
   |---|---|---|---|
   | `gemma4:12b-16k-cosmo` | 1.884s | 4.201s | 8.40 GB |
   | `gemma4:12b-32k-cosmo` | 1.906s | 4.258s | 8.42 GB |

   Peak prompt is ~2,355 tokens (Stage 138), which is 14% of the 16k window,
   so `num_ctx` never binds and the larger window costs nothing and buys
   nothing.

2. **Having both installed was actively harmful.** The GPU holds exactly one
   12B model (8.4 GB resident, 12.3 GB card), so naming the other tag forces a
   full unload and reload. Measured swap cost: **6.4s**, and it destroys the
   prefix cache on top of that. An earlier 16k-vs-32k comparison in this same
   slice was invalidated by exactly this - it measured swapping and was
   discarded.

`gemma4:12b-32k-cosmo` was selected. The tiebreak was not performance, since
there is none: it is what the deployed service env runs, what all three
production code sites already name, and what the 30/51 Stage 142 baseline was
measured on. Switching would have invalidated that baseline for no gain.

The others were removed from Ollama so they cannot be selected by accident -
from a stale script, an env override, or the Open WebUI model picker.

`Modelfile.qwen3.5-9b-32k-cosmo` was **reconstructed** from `ollama show`
before removal; it was installed but had never been checked in, so removing it
without capturing it first would have been unrecoverable.

## Restoring one

```
ollama create qwen3.5:9b-32k-cosmo -f archive/modelfiles/Modelfile.qwen3.5-9b-32k-cosmo
```

Base models (`gemma4:12b`, `qwen3.5:9b`, `phi4:14b`, `qwen3.5:2b`,
`qwen3.5:4b`) were left installed; they are upstream pulls rather than project
artifacts. `nomic-embed-text` is left installed and is **load-bearing** - RUDI
uses it for embeddings.
