// glsl_specsmooth: audio spectrum -> smoothed level, peak hold, instant level (8192 x 1).
// Input 0: chopto_spectrum, linear 0-22050 Hz magnitudes from audiospectrum_out.
// Input 1: feedback_spec, this shader's previous frame.
// Levels map dB onto 0-1 over a 96 dB range so every consumer shares one scale:
// R = smoothed (fast rise, slow fall), G = peak hold (falls uSmooth.z per frame), B = instant.
uniform vec4 uSmooth;   // rise blend, fall blend, peak fall per frame, dB offset

layout(location = 0) out vec4 fragColor;

void main() {
	ivec2 px = ivec2(gl_FragCoord.xy);
	float mag = texelFetch(sTD2DInputs[0], px, 0).r;
	vec4 prev = texelFetch(sTD2DInputs[1], px, 0);
	float db = 6.0206 * log2(max(mag, 1e-9)) + uSmooth.w;     // 20*log10(mag) + offset
	float level = clamp((db + 96.0) / 96.0, 0.0, 1.0);
	float smoothed = mix(prev.r, level, level > prev.r ? uSmooth.x : uSmooth.y);
	float peak = max(level, prev.g - uSmooth.z);
	fragColor = TDOutputSwizzle(vec4(smoothed, peak, level, 1.0));
}
