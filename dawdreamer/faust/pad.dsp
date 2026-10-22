// Pad: three detuned saws per side through a gentle low-pass; a slow attack and release keep it behind the hits.
declare name "pad";
declare voices "8";
declare release "3.0";
import("stdfaust.lib");

freq = hslider("freq", 220, 20, 20000, 0.01);
gain = hslider("gain", 1, 0, 1, 0.001);
gate = button("gate");
attack = hslider("attack", 0.35, 0.005, 4, 0.001);
release = hslider("release", 1.2, 0.05, 6, 0.001);
detune = hslider("detune", 0.006, 0, 0.03, 0.0001);
cutoff = hslider("cutoff", 2200, 200, 12000, 1);

env = en.adsre(attack, 1, 0.85, release, gate);
saws(d) = (os.sawtooth(freq * (1 - d)) + os.sawtooth(freq) + os.sawtooth(freq * (1 + d))) / 3;
side(d) = saws(d) : fi.lowpass(2, cutoff) : *(env * gain * 0.3);
process = side(detune), side(detune * 1.37);
effect = _, _;
