# Archived Modelfiles

Kept, not deleted: these are the only record of how the Stage 138 roster
models were built, and Stage 140 will need them if it reopens the model
comparison. Restoring one is a single command, which is what made the tag
decision below reversible when it turned out to be wrong.

## The capture model: 32k, then 16k

Retired `gemma4:12b-16k-cosmo` on 2026-08-29 and selected 32k. Reversed the
same day and selected **`gemma4:12b-16k-cosmo`**. Both decisions were correct
on the evidence available when they were made; what changed was the serving
configuration underneath them.

**First decision.** Measured in isolation, one model resident at a time, six
captures each after a discarded warmup, the two tags were indistinguishable:

| tag | prefill/capture | decode/capture | VRAM |
|---|---|---|---|
| `gemma4:12b-16k-cosmo` | 1.884s | 4.201s | 8.40 GB |
| `gemma4:12b-32k-cosmo` | 1.906s | 4.258s | 8.42 GB |

Peak prompt is ~2,355 tokens, 14% of the smaller window, so `num_ctx` never
binds. With no measurable difference the tiebreak fell to coherence, and 32k
was what deployment ran, what the code named, and what the baseline was
measured on.

**What reversed it.** The prefill sawtooth turned out to be a slot-count
artifact: the runner was launched `-np 1`, one sequence slot, so the capture
chain's two scaffolds evicted each other every call. Setting
`OLLAMA_NUM_PARALLEL=2` fixed that - and Ollama **multiplies** `num_ctx` by
the slot count rather than dividing it, so the window size stopped being free:

| config | VRAM used | free of 12,282 MiB |
|---|---|---|
| 32k, `-np 1`, f16 | 8,892 MiB | 3,390 |
| 32k, `-np 2`, f16 | 9,850 MiB | 2,432 |
| **16k, `-np 2`, `q8_0`** | **8,950 MiB** | **3,332** |

16k on two slots allocates what 32k did on one, and each slot still holds ~7x
the peak prompt. With `OLLAMA_KV_CACHE_TYPE=q8_0` on top, the server runs two
cached prefixes and keeps the headroom. That is a real difference where
previously there was none, so the tiebreak no longer applied.

**Why both tags are never installed together.** The card holds exactly one 12B
model (8.4 GB of 12.3 GB), so naming the other forces a full unload and
reload, measured at **6.4s**, and voids every cached prefix. An early
16k-vs-32k comparison was invalidated by precisely this - it measured swapping
- and was discarded. A guard test now fails if any source file names a
non-canonical tag.

`Modelfile.qwen3.5-9b-32k-cosmo` was **reconstructed** from `ollama show`
before removal; it was installed but had never been checked in, so removing it
without capturing it first would have been unrecoverable.

## Restoring one

```
ollama create gemma4:12b-32k-cosmo -f archive/modelfiles/Modelfile.gemma4-12b-32k-cosmo
```

Base models (`gemma4:12b`, `qwen3.5:9b`, `phi4:14b`, `qwen3.5:2b`,
`qwen3.5:4b`) are left installed; they are upstream pulls rather than project
artifacts. `nomic-embed-text` is left installed and is **load-bearing** - RUDI
uses it for embeddings during capture.
