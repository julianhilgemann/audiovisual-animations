// glsl_sono: scrolling sonogram, 512 frames (x, newest at the right) by 256
// log-frequency rows (y, uSono.x .. uSono.y Hz). Each frame every column moves one
// pixel left and the rightmost column is filled from the current spectrum.
// Input 0: null_specsmooth (B = instant level 0-1, linear 0..nyquist).
// Input 1: feedback_sono, this shader's previous frame.
uniform vec4 uSono;   // fmin Hz, fmax Hz, nyquist Hz, unused

layout(location = 0) out vec4 fragColor;

void main() {
	ivec2 px = ivec2(gl_FragCoord.xy);
	ivec2 res = ivec2(uTDOutputInfo.res.zw);
	if (px.x < res.x - 1) {
		fragColor = texelFetch(sTD2DInputs[1], px + ivec2(1, 0), 0);
		return;
	}
	float ratio = uSono.y / uSono.x;
	float f0 = uSono.x * pow(ratio, float(px.y) / float(res.y));
	float f1 = uSono.x * pow(ratio, float(px.y + 1) / float(res.y));
	float level = 0.0;
	for (int i = 0; i < 8; i++) {          // max over the row's frequency band
		float f = mix(f0, f1, (float(i) + 0.5) / 8.0);
		level = max(level, texture(sTD2DInputs[0], vec2(f / uSono.z, 0.5)).b);
	}
	fragColor = TDOutputSwizzle(vec4(level, level, level, 1.0));
}
