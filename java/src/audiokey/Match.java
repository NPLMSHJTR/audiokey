package audiokey;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Stream;

/**
 * Builds an inverted index of track fingerprints and answers clip queries.
 *
 * A query and a track that contain the same audio produce hashes at the same
 * relative offsets, so the winning hypothesis is the (track, offset) pair with
 * the most votes. Counting votes in offset space is what turns thousands of
 * accidental hash collisions into one confident answer.
 */
public final class Match {
    private static final int OFFSET = 1 << 19;

    record QueryResult(String query, String track, int votes, int second, double margin,
                       int hashes, double latencyMs) {}

    public static void main(String[] args) throws IOException {
        Path tracks = Path.of("data/tracks");
        Path queries = Path.of("data/queries");
        Path out = Path.of("data/results.json");
        int fanout = 8;
        double factor = 0.8;
        int perFrame = 6;
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--tracks" -> tracks = Path.of(args[++i]);
                case "--queries" -> queries = Path.of(args[++i]);
                case "--out" -> out = Path.of(args[++i]);
                case "--fanout" -> fanout = Integer.parseInt(args[++i]);
                case "--factor" -> factor = Double.parseDouble(args[++i]);
                case "--peaks" -> perFrame = Integer.parseInt(args[++i]);
                default -> {
                    System.err.println("unknown argument: " + args[i]);
                    System.exit(2);
                }
            }
        }

        List<Path> trackFiles = list(tracks);
        List<Path> queryFiles = list(queries);
        if (trackFiles.isEmpty() || queryFiles.isEmpty()) {
            System.err.println("need at least one track and one query");
            System.exit(2);
        }

        long buildStart = System.nanoTime();
        Map<Integer, List<Long>> index = new HashMap<>();
        long indexedHashes = 0;
        List<String> trackIds = new ArrayList<>();
        for (int trackIndex = 0; trackIndex < trackFiles.size(); trackIndex++) {
            Path file = trackFiles.get(trackIndex);
            trackIds.add(file.getFileName().toString().replace(".wav", ""));
            Map<Integer, List<Integer>> hashes = Dsp.hashes(Dsp.peaks(Dsp.spectrogram(Dsp.readWav(file)), factor, perFrame), fanout);
            for (Map.Entry<Integer, List<Integer>> entry : hashes.entrySet()) {
                List<Long> postings = index.computeIfAbsent(entry.getKey(), key -> new ArrayList<>());
                for (int frame : entry.getValue()) {
                    postings.add(((long) trackIndex << 32) | (frame & 0xffffffffL));
                    indexedHashes++;
                }
            }
        }
        double buildSeconds = (System.nanoTime() - buildStart) / 1e9;

        StringBuilder json = new StringBuilder();
        json.append("{\"schema_version\":1,\"fanout\":").append(fanout)
            .append(",\"tracks\":").append(trackFiles.size())
            .append(",\"indexed_hashes\":").append(indexedHashes)
            .append(",\"build_s\":").append(String.format(Locale.ROOT, "%.3f", buildSeconds))
            .append(",\"queries\":[");

        for (int queryIndex = 0; queryIndex < queryFiles.size(); queryIndex++) {
            Path file = queryFiles.get(queryIndex);
            long started = System.nanoTime();
            Map<Integer, List<Integer>> hashes =
                Dsp.hashes(Dsp.peaks(Dsp.spectrogram(Dsp.readWav(file)), factor, perFrame), fanout);

            Map<Long, Integer> votes = new HashMap<>();
            int hashCount = 0;
            for (Map.Entry<Integer, List<Integer>> entry : hashes.entrySet()) {
                List<Long> postings = index.get(entry.getKey());
                if (postings == null) {
                    continue;
                }
                for (int queryFrame : entry.getValue()) {
                    hashCount++;
                    for (long posting : postings) {
                        int trackIndex = (int) (posting >>> 32);
                        int trackFrame = (int) (posting & 0xffffffffL);
                        int offset = trackFrame - queryFrame + OFFSET;
                        long key = ((long) trackIndex << 20) | offset;
                        votes.merge(key, 1, Integer::sum);
                    }
                }
            }

            long bestKey = -1;
            int best = 0;
            int second = 0;
            for (Map.Entry<Long, Integer> entry : votes.entrySet()) {
                int value = entry.getValue();
                if (value > best) {
                    second = Math.max(second, best);
                    best = value;
                    bestKey = entry.getKey();
                } else if (value > second) {
                    second = value;
                }
            }
            String track = bestKey < 0 ? "" : trackIds.get((int) (bestKey >>> 20));
            double margin = best == 0 ? 0 : best / (double) Math.max(1, second);
            double latency = (System.nanoTime() - started) / 1e6;

            if (queryIndex > 0) {
                json.append(',');
            }
            json.append("{\"query\":").append(quote(file.getFileName().toString()))
                .append(",\"track\":").append(quote(track))
                .append(",\"votes\":").append(best)
                .append(",\"second\":").append(second)
                .append(",\"margin\":").append(String.format(Locale.ROOT, "%.2f", margin))
                .append(",\"hashes\":").append(hashCount)
                .append(",\"latency_ms\":").append(String.format(Locale.ROOT, "%.2f", latency))
                .append('}');
        }
        json.append("]}\n");
        if (out.getParent() != null) {
            Files.createDirectories(out.getParent());
        }
        Files.writeString(out, json.toString(), StandardCharsets.UTF_8);

        System.out.println(String.format(Locale.ROOT,
            "indexed %d tracks (%d hashes) in %.2f s; matched %d queries",
            trackFiles.size(), indexedHashes, buildSeconds, queryFiles.size()));
    }

    private static List<Path> list(Path directory) throws IOException {
        try (Stream<Path> stream = Files.list(directory)) {
            return stream.filter(path -> path.toString().endsWith(".wav"))
                .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                .toList();
        }
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '"' || c == '\\') {
                out.append('\\');
            }
            out.append(c);
        }
        return out.append('"').toString();
    }
}
