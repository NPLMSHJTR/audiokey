package audiokey;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Audio fingerprinting: WAV reading, STFT, spectral peak picking, and hashing.
 *
 * The fingerprint is a set of (f1, f2, dt) triples describing pairs of spectral
 * peaks. A pair is robust to gain and to additive noise because both change
 * magnitudes rather than peak positions; a single peak is not, because gain and
 * noise move its rank.
 */
public final class Dsp {
    static final int SAMPLE_RATE = 8000;
    static final int WINDOW = 512;
    static final int HOP = 128;
    static final int BINS = WINDOW / 2;

    record Peak(int frame, int bin, double magnitude) {}

    private Dsp() {}

    static short[] readWav(Path path) throws IOException {
        byte[] bytes = Files.readAllBytes(path);
        if (bytes.length < 44 || bytes[0] != 'R' || bytes[1] != 'I' || bytes[2] != 'F' || bytes[3] != 'F') {
            throw new IOException("not a RIFF file: " + path);
        }
        ByteBuffer buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        int offset = 12;
        int format = 0;
        int channels = 1;
        int bits = 16;
        int dataOffset = -1;
        int dataLength = 0;
        while (offset + 8 <= bytes.length) {
            String id = new String(bytes, offset, 4, java.nio.charset.StandardCharsets.US_ASCII);
            int size = buffer.getInt(offset + 4);
            int body = offset + 8;
            if (id.equals("fmt ")) {
                format = buffer.getShort(body) & 0xffff;
                channels = buffer.getShort(body + 2) & 0xffff;
                bits = buffer.getShort(body + 14) & 0xffff;
            } else if (id.equals("data")) {
                dataOffset = body;
                dataLength = Math.min(size, bytes.length - body);
                break;
            }
            offset = body + size + (size % 2);
        }
        if (dataOffset < 0 || format != 1 || bits != 16) {
            throw new IOException("expected 16-bit PCM WAV: " + path);
        }
        int frames = dataLength / (2 * channels);
        short[] samples = new short[frames];
        for (int i = 0; i < frames; i++) {
            samples[i] = buffer.getShort(dataOffset + i * 2 * channels);
        }
        return samples;
    }

    static double[][] spectrogram(short[] samples) {
        int frames = Math.max(0, (samples.length - WINDOW) / HOP + 1);
        double[][] magnitudes = new double[frames][BINS];
        double[] window = new double[WINDOW];
        for (int i = 0; i < WINDOW; i++) {
            window[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (WINDOW - 1));
        }
        double[] real = new double[WINDOW];
        double[] imaginary = new double[WINDOW];
        for (int frame = 0; frame < frames; frame++) {
            int start = frame * HOP;
            for (int i = 0; i < WINDOW; i++) {
                real[i] = samples[start + i] * window[i] / 32768.0;
                imaginary[i] = 0;
            }
            fft(real, imaginary);
            for (int bin = 0; bin < BINS; bin++) {
                magnitudes[frame][bin] = Math.log10(1 + Math.hypot(real[bin], imaginary[bin]) * 1000);
            }
        }

        return magnitudes;
    }

    static double median(double[] values) {
        if (values.length == 0) {
            return 0;
        }
        double[] copy = values.clone();
        Arrays.sort(copy);
        return copy[copy.length / 2];
    }

    static void fft(double[] real, double[] imaginary) {
        int n = real.length;
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >> 1;
            for (; (j & bit) != 0; bit >>= 1) {
                j ^= bit;
            }
            j ^= bit;
            if (i < j) {
                double temp = real[i];
                real[i] = real[j];
                real[j] = temp;
                temp = imaginary[i];
                imaginary[i] = imaginary[j];
                imaginary[j] = temp;
            }
        }
        for (int length = 2; length <= n; length <<= 1) {
            double angle = -2 * Math.PI / length;
            double wReal = Math.cos(angle);
            double wImaginary = Math.sin(angle);
            for (int i = 0; i < n; i += length) {
                double curReal = 1;
                double curImaginary = 0;
                for (int j = 0; j < length / 2; j++) {
                    int u = i + j;
                    int v = i + j + length / 2;
                    double vr = real[v] * curReal - imaginary[v] * curImaginary;
                    double vi = real[v] * curImaginary + imaginary[v] * curReal;
                    real[v] = real[u] - vr;
                    imaginary[v] = imaginary[u] - vi;
                    real[u] += vr;
                    imaginary[u] += vi;
                    double nextReal = curReal * wReal - curImaginary * wImaginary;
                    curImaginary = curReal * wImaginary + curImaginary * wReal;
                    curReal = nextReal;
                }
            }
        }
    }

    static List<Peak> peaks(double[][] spectrogram, double factor, int perFrame) {
        List<Peak> peaks = new ArrayList<>();
        int frames = spectrogram.length;
        if (frames == 0) {
            return peaks;
        }

        for (int frame = 0; frame < frames; frame++) {
            // A global threshold fails under additive noise: the noise floor
            // rises everywhere, the threshold rises with it, and quiet frames
            // stop contributing peaks. A per-frame threshold keeps every frame
            // scaled to its own noise level.
            double sum = 0;
            double square = 0;
            int count = 0;
            for (int bin = 2; bin < BINS; bin++) {
                sum += spectrogram[frame][bin];
                square += spectrogram[frame][bin] * spectrogram[frame][bin];
                count++;
            }
            double mean = sum / count;
            double deviation = Math.sqrt(Math.max(0, square / count - mean * mean));
            double floor = mean + factor * deviation;

            List<Peak> local = new ArrayList<>();
            for (int bin = 2; bin < BINS - 2; bin++) {
                double value = spectrogram[frame][bin];
                if (value < floor) {
                    continue;
                }
                boolean isPeak = true;
                for (int df = -2; df <= 2 && isPeak; df++) {
                    int f = frame + df;
                    if (f < 0 || f >= frames) {
                        continue;
                    }
                    for (int db = -2; db <= 2; db++) {
                        int b = bin + db;
                        if (b < 0 || b >= BINS || (df == 0 && db == 0)) {
                            continue;
                        }
                        if (spectrogram[f][b] > value) {
                            isPeak = false;
                            break;
                        }
                    }
                }
                if (isPeak) {
                    local.add(new Peak(frame, bin, value));
                }
            }
            local.sort((a, b) -> Double.compare(b.magnitude, a.magnitude));
            peaks.addAll(local.subList(0, Math.min(perFrame, local.size())));
        }
        return peaks;
    }

    /** Packs a peak pair into one int: 9 bits per frequency, 6 bits of time delta. */
    static int pairHash(Peak first, Peak second, int deltaSeconds) {
        return (first.bin() << 15) | (second.bin() << 6) | Math.min(63, deltaSeconds);
    }

    static Map<Integer, List<Integer>> hashes(List<Peak> peaks, int fanout) {
        Map<Integer, List<Integer>> table = new HashMap<>();
        int frameRate = SAMPLE_RATE / HOP;
        for (int i = 0; i < peaks.size(); i++) {
            Peak anchor = peaks.get(i);
            int paired = 0;
            for (int j = i + 1; j < peaks.size() && paired < fanout; j++) {
                Peak target = peaks.get(j);
                int deltaFrames = target.frame() - anchor.frame();
                if (deltaFrames <= 0) {
                    continue;
                }
                if (deltaFrames > 63) {
                    break;
                }
                if (Math.abs(target.bin() - anchor.bin()) > 40) {
                    continue;
                }
                int seconds = (int) Math.round(deltaFrames * 1000.0 / frameRate);
                table.computeIfAbsent(pairHash(anchor, target, seconds), key -> new ArrayList<>())
                    .add(anchor.frame());
                paired++;
            }
        }
        return table;
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 0 || !args[0].equals("hash")) {
            System.err.println("usage: Dsp hash <file.wav>");
            System.exit(2);
        }
        short[] samples = readWav(Path.of(args[1]));
        double[][] spec = spectrogram(samples);
        List<Peak> peaks = peaks(spec, 0.8, 6);
        Map<Integer, List<Integer>> table = hashes(peaks, 5);
        System.out.println(String.format(Locale.ROOT,
            "%s: %d samples, %d frames, %d peaks, %d hashes",
            Path.of(args[1]).getFileName(), samples.length, spec.length, peaks.size(), table.size()));
    }
}
