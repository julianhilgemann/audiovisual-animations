// Space: Zita reverb, fully wet, for a return bus. A high-pass on the way in keeps the low end out of the tail.
declare name "space";
import("stdfaust.lib");

decay = hslider("decay", 2.4, 0.2, 12, 0.01);
predelay = hslider("predelay", 20, 1, 200, 0.1);
lowcut = hslider("lowcut", 300, 20, 2000, 1);
damp = hslider("damp", 5500, 1000, 20000, 1);

inp = fi.highpass(2, lowcut);
process = inp, inp : re.zita_rev1_stereo(predelay, 200, damp, decay, decay * 0.8, 48000);
