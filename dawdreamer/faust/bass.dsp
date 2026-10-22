// Bass: a sine for the low end plus a filtered, saturated saw whose harmonics carry the line on phone speakers.
// One voice, so a new note takes over the old one; `glide` slides between them.
declare name "bass";
declare voices "1";
declare release "0.3";
import("stdfaust.lib");

freq = hslider("freq", 55, 20, 2000, 0.01);
gain = hslider("gain", 1, 0, 1, 0.001);
gate = button("gate");
cutoff = hslider("cutoff", 500, 50, 8000, 1);
env_mod = hslider("env_mod", 3, 0, 12, 0.01);
res = hslider("res", 0.3, 0, 0.95, 0.01);
decay = hslider("decay", 0.18, 0.02, 2, 0.001);
sustain = hslider("sustain", 0.8, 0, 1, 0.01);
drive = hslider("drive", 2.5, 1, 10, 0.01);
sub = hslider("sub", 0.6, 0, 1, 0.01);
glide = hslider("glide", 0, 0, 0.3, 0.001);

f = freq : si.smooth(ba.tau2pole(glide));
amp = en.adsre(0.003, 0.4, sustain, 0.04, gate);
fenv = en.adsre(0.001, decay, 0, 0.05, gate);
fc = min(cutoff * (1 + env_mod * fenv), 16000);
grit = os.sawtooth(f) : ve.moog_vcf_2bn(res, fc) : *(drive) : ma.tanh;
process = (grit * 0.5 + os.osc(f) * sub) * amp * gain * 0.75 <: _, _;
effect = _, _;
