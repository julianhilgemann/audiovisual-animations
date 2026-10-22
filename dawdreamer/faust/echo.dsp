// Echo: a tempo-synced ping-pong delay, fully wet, for a return bus. The engine sets `bpm` from the score;
// `beats` is the delay time (0.75 = dotted eighth). Repeats lose highs through `tone`.
declare name "echo";
import("stdfaust.lib");

bpm = hslider("bpm", 120, 30, 300, 0.01);
beats = hslider("beats", 0.75, 0.0625, 4, 0.0001);
feedback = hslider("feedback", 0.4, 0, 0.95, 0.01);
tone = hslider("tone", 3500, 300, 16000, 1);
lowcut = hslider("lowcut", 300, 20, 2000, 1);

maxd = 524288;
d = int(beats * 60 / bpm * ma.SR);
loop = + ~ (de.delay(maxd, 2 * d - 1) : fi.lowpass(1, tone) : *(feedback));
process(l, r) = (l + r) * 0.5 : fi.highpass(2, lowcut) : loop <: de.delay(maxd, d), de.delay(maxd, 2 * d);
