// glsl_presence: modulator-video mask + motion trail at 128x128.
// Input 0: null_cam (video now)     Input 1: null_bg (learned background)
// Input 2: feedback_prev (camera one frame ago)
// Input 3: feedback_presence (this shader's previous output)
// Out: R = mask 0-1 (soft key, smoothed over time)
//      G = motion trail 0-1 (frame difference that decays)
//      B = camera luma, A = 1
// Not mirrored: the field shader and script_features apply Mirror.
uniform vec4 uKey;     // x threshold, y softness, z mode (0 bright parts, 1 dark parts, 2 background difference), w mask smoothing
uniform vec4 uMotion;  // x trail decay per frame, y motion threshold, z motion gain, w video on (0/1)

layout(location = 0) out vec4 fragColor;

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

void main() {
	vec2 uv = vUV.st;
	vec3 cam = texture(sTD2DInputs[0], uv).rgb;
	vec3 bg = texture(sTD2DInputs[1], uv).rgb;
	vec3 prev = texture(sTD2DInputs[2], uv).rgb;
	vec4 last = texture(sTD2DInputs[3], uv);
	float d;
	if (uKey.z < 0.5) {
		d = luma(cam);                // bright parts (label, highlights on the grooves)
	} else if (uKey.z < 1.5) {
		d = 1.0 - luma(cam);          // dark parts (the record itself on a light ground)
	} else {
		d = length(cam - bg) * 0.8 + abs(luma(cam) - luma(bg)) * 0.6;   // distance to the learned background
	}
	float mask = smoothstep(uKey.x - uKey.y, uKey.x + uKey.y, d) * uMotion.w;
	mask = mix(mask, last.r, uKey.w);
	float m = smoothstep(uMotion.y, uMotion.y * 4.0, length(cam - prev)) * uMotion.w;
	float trail = max(m * uMotion.z, last.g * uMotion.x);
	fragColor = TDOutputSwizzle(vec4(mask, clamp(trail, 0.0, 1.0), luma(cam), 1.0));
}
