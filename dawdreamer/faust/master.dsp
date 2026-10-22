// Master: the side signal below `mono_hz` removed (bass in mono), then a gentle glue compressor.
// The engine feeds it the mix at -18 LUFS, so `thresh` means the same for every preset.
// Loudness (-14 LUFS) and the true-peak ceiling come after, in Python (datapipe.gen.master).
declare name "master";
import("stdfaust.lib");

mono_hz = hslider("mono_hz", 120, 20, 400, 1);
ratio = hslider("ratio", 2, 1, 10, 0.01);
thresh = hslider("thresh", -9, -40, 0, 0.1);
attack = hslider("attack", 0.02, 0.0005, 0.2, 0.0001);
release = hslider("release", 0.15, 0.01, 2, 0.001);

monobass(l, r) = m + s, m - s
with {
    m = (l + r) * 0.5;
    s = (l - r) * 0.5 : fi.highpass(2, mono_hz);
};
process = monobass : co.compressor_stereo(ratio, thresh, attack, release);
