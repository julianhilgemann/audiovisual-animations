// Impact: a deep boom whose pitch falls from `high` to `low`, plus a low-passed noise burst.
// For the downbeat that resolves the loop.
declare name "impact";
declare voices "1";
declare release "3.0";
import("stdfaust.lib");

gain = hslider("gain", 1, 0, 1, 0.001);
gate = button("gate");
low = hslider("low", 40, 20, 100, 0.1);
high = hslider("high", 120, 40, 400, 0.1);
decay = hslider("decay", 1.4, 0.2, 6, 0.01);
noise = hslider("noise", 0.35, 0, 1, 0.01);

trig = gate : ba.impulsify;
fall(t60) = trig : fi.pole(ba.tau2pole(t60 / 6.91));
phase(f) = f / ma.SR : (+ : ma.frac) ~ *(1 - trig);
boom = sin(2 * ma.PI * phase(low + (high - low) * fall(0.3))) * fall(decay);
burst(n) = n : fi.lowpass(2, 2500) : *(fall(0.35) * noise);
process = no.multinoise(2) : burst, burst : +(boom), +(boom) : ma.tanh, ma.tanh : *(gain * 0.8), *(gain * 0.8);
effect = _, _;
