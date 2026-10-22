// Kick: a sine swept down from `sweep` x `tune` to `tune`, a noise click on top, tanh drive.
// The phase restarts on every note-on, so every hit is identical.
declare name "kick";
declare voices "2";
declare release "1.5";
import("stdfaust.lib");

gain = hslider("gain", 1, 0, 1, 0.001);
gate = button("gate");
tune = hslider("tune", 48, 30, 100, 0.1);
sweep = hslider("sweep", 4, 1, 10, 0.01);
pitch_decay = hslider("pitch_decay", 0.03, 0.005, 0.3, 0.001);
decay = hslider("decay", 0.4, 0.05, 2, 0.001);
click = hslider("click", 0.4, 0, 1, 0.01);
drive = hslider("drive", 2, 1, 8, 0.01);

trig = gate : ba.impulsify;
fall(t60) = trig : fi.pole(ba.tau2pole(t60 / 6.91));
phase(f) = f / ma.SR : (+ : ma.frac) ~ *(1 - trig);
body = sin(2 * ma.PI * phase(tune * (1 + (sweep - 1) * fall(pitch_decay)))) * fall(decay);
tick = no.noise : fi.highpass(2, 2000) : *(fall(0.006) * click);
process = (body + tick) * drive : ma.tanh : /(ma.tanh(drive)) : *(gain * 0.9) <: _, _;
effect = _, _;
