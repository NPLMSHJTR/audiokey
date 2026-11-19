# audiokey

**Recognise a clip from five seconds of noisy audio.** `audiokey` builds a
fingerprint index from spectral peak pairs and votes each query into
(track, time-offset) space. It reports rank-1 accuracy per distortion condition,
because an average over clean and noisy clips hides exactly the thing worth
knowing.

```console
$ python scripts/demo.py
audiokey 0.1.0  12 tracks  60 queries
accuracy 80.0% (48/60)  median latency 11.1 ms  margin 1.63x
  clean    24/24  100%
  gain     12/12  100%
  noise15  7/12  58%
  noise5   5/12  42%
```

## How it works

| Stage | Implementation |
| --- | --- |
| audio | 8 kHz, 16-bit mono WAV, parsed by hand (no `javax.sound`) |
| spectrum | 512-sample Hann window, 128-sample hop, radix-2 FFT, log magnitude |
| peaks | local maxima in a 5×5 neighbourhood, per-frame threshold, 6 per frame |
| hash | pairs of peaks within 1 s and 40 bins, packed into one int |
| index | hash → list of (track, frame) |
| match | histogram of `track_frame − query_frame`, best bucket wins |

Hashing **pairs** rather than single peaks is what makes the fingerprint survive
gain changes: gain scales every magnitude, so peak ranks move, but the
relationship between two peaks does not. The offset histogram is what turns
thousands of accidental hash collisions into one confident answer — real matches
agree on a single offset, collisions scatter.

## Results

12 tracks × 20 s, 60 query clips, 12 per condition. One JVM, no GPU.

| Query length | Accuracy | Clean | Gain | Noise 15 dB | Noise 5 dB |
| --- | --- | --- | --- | --- | --- |
| 3 s | 76.7% | 24/24 | 12/12 | 6/12 | 4/12 |
| 5 s | 80.0% | 24/24 | 12/12 | 7/12 | 5/12 |
| 8 s | 85.0% | 24/24 | 12/12 | 10/12 | 5/12 |

Index: 73,245 hashes for 12 tracks, built in 0.26 s. Median query latency 11 ms
at 5 s, 18 ms at 8 s.

The pattern is the honest one: amplitude changes cost nothing, moderate noise is
a matter of how much evidence the clip carries, and 5 dB SNR is beyond what a
5-second clip can support with this feature set.

## What did not work

Two standard tricks were tried and rejected on measurement, not on taste:

- **Spectral whitening** (subtract each frequency bin's median over time) removed
  stationary noise as intended, but it also removed the sustained chord tones.
  Accuracy fell from 0.800 to 0.700, so the code was reverted.
- **Frequency quantisation** (bins divided by two) was meant to absorb ±1-bin
  drift under noise. At 5 s it fell to 0.717 and at 8 s to 0.833, so it was
  reverted too.

Both experiments are described here because a repository that only reports its
successful ideas is hiding the cost of finding them.

## Quick start

```bash
python scripts/demo.py
```

Step by step:

```bash
PYTHONPATH=python/src python -m audiokey gen --tracks 12 --clip 5 \
  --tracks-dir data/tracks --queries-dir data/queries --truth data/truth.json
javac -d out java/src/audiokey/*.java
java -cp out audiokey.Match --tracks data/tracks --queries data/queries --out data/results.json
PYTHONPATH=python/src python -m audiokey eval \
  --truth data/truth.json --results data/results.json --out reports
```

Requirements: JDK 22 for the DSP, Python 3.11+ for synthesis and scoring, Node
22.6+ only if you want the dashboard.

## What the catalogue sounds like

Each track is a four-chord loop (I–V–vi–IV) in a random key, with a pentatonic
melody on top, decaying note envelopes, and a low noise floor. Queries are
5-second excerpts with one of four treatments:

- **clean** — no change
- **gain** — scaled by 0.45× or 2.2×, clipped at 16-bit limits
- **noise15** — additive Gaussian noise at 15 dB SNR
- **noise5** — additive Gaussian noise at 5 dB SNR

## Limits

- **Synthetic catalogue.** Twelve 20-second loops with strong harmonic structure
  are easier than real music with drums, vocals, and silence.
- **8 kHz mono.** Speech-grade audio keeps the demo fast; real systems work at
  44.1 kHz and use more peaks per second.
- **No streaming.** The whole index is rebuilt per run; there is no incremental
  insert, no persistence, no sharding.
- **5 dB is a wall.** Inference-time tricks do not fix a signal-to-noise problem;
  longer clips or a better front end would.

## Repository layout

```
java/src/audiokey/Dsp.java       WAV, FFT, spectrogram, peaks, hashing
java/src/audiokey/Match.java     index build, offset voting, JSON output
python/src/audiokey/gen.py       track synthesis and query generation
python/src/audiokey/evaluate.py  rank-1 accuracy by condition
web/dashboard.ts                 single-file result dashboard
scripts/demo.py                  the whole pipeline in one command
```

## Development

```bash
PYTHONPATH=python/src python -m unittest discover -s python/tests -t python/tests -v
cd python && pip install -e ".[dev]" && ruff check . && mypy
```

## License

MIT. See [LICENSE](LICENSE).
