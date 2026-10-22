// Riser: band-passed noise whose centre climbs from `low` to `high` and whose level grows with `amount`.
// Not a MIDI instrument: automate `amount` (0 to 1) from the score's riser curve.
declare name "riser";
import("stdfaust.lib");

amount = hslider("amount", 0, 0, 1, 0.0001) : si.smoo;
low = hslider("low", 250, 50, 2000, 1);
high = hslider("high", 9000, 1000, 16000, 1);
level = hslider("level", 0.6, 0, 1, 0.001);

fc = low * pow(high / low, amount);
sweep(n) = n : fi.resonbp(fc, 1.8, 1) : *(amount * amount * level);
process = no.multinoise(2) : sweep, sweep;
