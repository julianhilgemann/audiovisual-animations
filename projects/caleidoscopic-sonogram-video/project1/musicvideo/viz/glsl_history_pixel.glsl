// glsl_history: ring buffer of what the room hears, N columns (time) x M rows (content).
// Column = one moment; the write head (uHead.x) advances with Flow Speed and the
// field shader reads the ring backwards from it, in whichever screen direction.
// Rows: R and G use log frequency (uSono.x .. uSono.y Hz, bottom = low),
//       B uses scope phase (0 .. 1 of one drone cycle, bottom = cycle start).
// Input 0: null_specsmooth  drone spectrum, R = smoothed level 0-1, linear 0..nyquist
// Input 1: null_micsmooth   room-mic spectrum, same encoding
// Input 2: chopto_scope     one synced drone cycle, R = -1..1
// Input 3: feedback_history this shader's previous frame
// Out: R = drone level, G = room level, B = scope value, A = 1.
// Static (uHead.z = 1): nothing travels; every column relaxes toward the live
// content, fast at the head and slower with distance, so the field breathes.
uniform vec4 uHead;   // x head column (float), y columns written this frame, z static 0/1, w unused
uniform vec4 uSono;   // x fmin Hz, y fmax Hz, z nyquist Hz, w display tilt (level per octave above 500 Hz)

layout(location = 0) out vec4 fragColor;

float bandLevel(int input_index, float f0, float f1) {
	float level = 0.0;
	for (int i = 0; i < 6; i++) {               // max over the row's frequency band
		float f = mix(f0, f1, (float(i) + 0.5) / 6.0);
		if (input_index == 0) {
			level = max(level, texture(sTD2DInputs[0], vec2(f / uSono.z, 0.5)).r);
		} else {
			level = max(level, texture(sTD2DInputs[1], vec2(f / uSono.z, 0.5)).r);
		}
	}
	return level;
}

void main() {
	ivec2 px = ivec2(gl_FragCoord.xy);
	ivec2 res = ivec2(uTDOutputInfo.res.zw);
	vec4 prev = texelFetch(sTD2DInputs[3], px, 0);

	float ratio = uSono.y / uSono.x;
	float f0 = uSono.x * pow(ratio, float(px.y) / float(res.y));
	float f1 = uSono.x * pow(ratio, float(px.y + 1) / float(res.y));
	float phase = (float(px.y) + 0.5) / float(res.y);
	float tilt = uSono.w * log2(0.5 * (f0 + f1) / 500.0);     // like +3 dB/oct: highs are not drowned by the bass
	vec4 live = vec4(bandLevel(0, f0, f1) + tilt, bandLevel(1, f0, f1) + tilt,
	                 texture(sTD2DInputs[2], vec2(phase, 0.5)).r, 1.0);
	live.rg = clamp(live.rg, 0.0, 1.0);

	float n = float(res.x);
	float age = mod(floor(uHead.x) - float(px.x), n);       // 0 = newest column
	vec4 outc;
	if (uHead.z > 0.5) {
		float rate = mix(0.35, 0.004, pow(age / n, 0.5));
		outc = mix(prev, live, rate);
	} else if (age < max(1.0, ceil(uHead.y))) {
		outc = live;
	} else {
		outc = prev;
	}
	outc.a = 1.0;
	fragColor = TDOutputSwizzle(outc);
}
