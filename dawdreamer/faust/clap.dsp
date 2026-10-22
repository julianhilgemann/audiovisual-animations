// Clap: three short noise bursts `spread` seconds apart into a decaying tail, band-passed around `tone`.
// Left and right get independent noise, so the clap is wide.
declare name "clap";
declare voices "2";
declare release "1.0";
import("stdfaust.lib");

gain = hslider("gain", 1, 0, 1, 0.001);
gate = button("gate");
tone = hslider("tone", 1300, 400, 4000, 1);
decay = hslider("decay", 0.25, 0.05, 2, 0.001);
spread = hslider("spread", 0.011, 0.004, 0.03, 0.0001);

trig = gate : ba.impulsify;
at(t) = trig : de.delay(8192, int(t * ma.SR));
burst(t) = at(t) : fi.pole(ba.tau2pole(0.0025));
env = burst(0) + burst(spread) + burst(2 * spread) + 0.7 * (at(3 * spread) : fi.pole(ba.tau2pole(decay / 6.91)));
clap(n) = n * env : fi.resonbp(tone, 1.4, 1) : fi.highpass(2, 500) : *(gain * 1.6);
process = no.multinoise(2) : clap, clap;
effect = _, _;
