// Hi-hat: six square waves at the TR-808's inharmonic frequencies plus a little noise, band-passed high.
// Notes below 44 play closed (42 is the closed-hat note), 44 and up open (46).
declare name "hat";
declare voices "4";
declare release "1.0";
import("stdfaust.lib");

freq = hslider("freq", 185, 20, 20000, 0.01);
gain = hslider("gain", 1, 0, 1, 0.001);
gate = button("gate");
closed = hslider("closed", 0.045, 0.01, 0.5, 0.001);
open = hslider("open", 0.3, 0.05, 2, 0.001);
tone = hslider("tone", 9000, 3000, 16000, 1);
pitch = hslider("pitch", 1, 0.5, 2, 0.001);
noise = hslider("noise", 0.3, 0, 1, 0.01);

decay = select2(freq > ba.midikey2hz(43.5), closed, open);
trig = gate : ba.impulsify;
env = trig : fi.pole(ba.tau2pole(decay / 6.91));
metal = par(i, 6, os.square(pitch * ba.take(i + 1, (205.3, 304.4, 369.6, 522.7, 540.0, 800.0)))) :> /(6);
process = metal + no.noise * noise : fi.resonbp(tone, 1.0, 1) : fi.highpass(2, 7000) : *(env * gain * 2.2) <: _, _;
effect = _, _;
