// Filter: a resonant stereo low-pass. Automate `cutoff` from a score curve to open it through the build.
declare name "filter";
import("stdfaust.lib");

cutoff = hslider("cutoff", 18000, 20, 20000, 0.1) : si.smoo;
res = hslider("res", 0.2, 0, 0.95, 0.01);

process = ve.moog_vcf_2bn(res, cutoff), ve.moog_vcf_2bn(res, cutoff);
