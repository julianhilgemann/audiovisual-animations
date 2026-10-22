// Glass: a two-operator phase-modulation pluck. A fast-falling modulation index over a slower amplitude decay
// gives the bright, glassy attack; `ratio` 3.5 rings like a bell, 2 like a tine, 1 like a soft key.
// Left and right are detuned by `width` for a wide image.
declare name "glass";
declare voices "8";
declare release "2.0";
import("stdfaust.lib");

freq = hslider("freq", 440, 20, 20000, 0.01);
gain = hslider("gain", 1, 0, 1, 0.001);
gate = button("gate");
ratio = hslider("ratio", 3.5, 0.5, 12, 0.001);
index = hslider("index", 2.2, 0, 12, 0.01);
bright = hslider("bright", 0.18, 0.01, 2, 0.001);
decay = hslider("decay", 0.8, 0.05, 6, 0.001);
release = hslider("release", 0.3, 0.01, 4, 0.001);
width = hslider("width", 0.003, 0, 0.02, 0.0001);
shimmer = hslider("shimmer", 0.12, 0, 1, 0.01);

amp = en.adsre(0.0015, decay, 0, release, gate);
ienv = en.adsre(0.0005, bright, 0.08, release, gate);
ph(f) = os.phasor(1, f);
op(f) = sin(2 * ma.PI * ph(f) + index * ienv * sin(2 * ma.PI * ph(f * ratio)));
top = sin(2 * ma.PI * ph(2 * freq)) * en.adsre(0.001, decay * 0.4, 0, release, gate) * shimmer;
side(d) = (op(freq * (1 + d)) + top) * amp * gain * 0.55;
process = side(0 - width), side(width);
effect = _, _;
