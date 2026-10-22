// Drive: tanh saturation into a one-pole tone filter; `mix` blends it with the dry signal.
declare name "drive";
import("stdfaust.lib");

drive = hslider("drive", 2, 1, 20, 0.01);
tone = hslider("tone", 6000, 500, 20000, 1);
mix = hslider("mix", 1, 0, 1, 0.01);

sat = *(drive) : ma.tanh : /(ma.tanh(drive)) : fi.lowpass(1, tone);
channel = _ <: *(1 - mix), sat * mix :> _;
process = channel, channel;
