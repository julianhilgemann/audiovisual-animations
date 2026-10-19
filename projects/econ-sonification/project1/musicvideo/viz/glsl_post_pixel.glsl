// glsl_post: the finish of the music video (square).
// Input 0: bloom_cloud (sharp render + bloom)   Input 1: blur_defocus (its blur)
// Input 2: feedback_post (buffer 1 of the previous frame via null_trail: the light trails)
// Input 3: null_cam (the modulator video, for the optional ghost overlay)
// Order: glitch slices (high band) -> defocus mix (mid band) -> colour split (transients)
// -> exposure + filmic (ACES approx) tone map -> monochrome -> black crush + contrast curve
// -> trails (max with the decayed previous frame) -> strobe / invert (transients)
// -> vignette -> grain.
uniform vec4 uPost;    // x defocus 0-1, y colour split, z grain amount, w exposure
uniform vec4 uTime;    // x frame counter (grain and glitch seed)
uniform vec4 uGrade;   // x saturation, y black crush, z contrast curve (gamma), w trails decay
uniform vec4 uHit;     // x strobe 0-1, y invert 0-1, z glitch 0-1, w video ghost

layout(location = 0) out vec4 fragColor;
layout(location = 1) out vec4 fragTrail;   // buffer 1: the graded frame before the hits -> trail memory

float hash12(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

void main() {
	vec2 uv = vUV.st;
	vec2 d = uv - 0.5;

	// glitch: horizontal slices jump sideways, re-rolled a few times a second
	float slice = floor(uv.y * 48.0);
	float roll = floor(uTime.x / 4.0);
	float gate = step(1.0 - 0.35 * uHit.z, hash12(vec2(slice, roll)));
	vec2 guv = uv + vec2((hash12(vec2(slice * 1.7, roll + 3.0)) - 0.5) * 0.12 * uHit.z * gate, 0.0);

	vec2 off = d * uPost.y * 0.03;
	vec3 sharp = vec3(texture(sTD2DInputs[0], guv + off).r, texture(sTD2DInputs[0], guv).g, texture(sTD2DInputs[0], guv - off).b);
	vec3 soft = vec3(texture(sTD2DInputs[1], guv + off * 1.5).r, texture(sTD2DInputs[1], guv).g, texture(sTD2DInputs[1], guv - off * 1.5).b);
	vec3 c = mix(sharp, soft, clamp(uPost.x, 0.0, 1.0)) + soft * 0.12;
	c += uHit.w * 0.35 * luma(texture(sTD2DInputs[3], uv).rgb);
	c *= uPost.w;
	c = (c * (2.51 * c + 0.03)) / (c * (2.43 * c + 0.59) + 0.14);
	c = mix(vec3(luma(c)), c, uGrade.x);
	c = pow(clamp((c - uGrade.y) / max(1e-3, 1.0 - uGrade.y), 0.0, 1.0), vec3(uGrade.z));

	vec3 prev = texture(sTD2DInputs[2], uv).rgb;
	c = max(c, prev * uGrade.w);

	vec3 hit = c;
	hit = hit * (1.0 + 2.5 * uHit.x) + uHit.x * 0.04;          // strobe: the light punches, black stays black
	hit = mix(hit, 1.0 - hit, uHit.y);
	hit *= 1.0 - 0.4 * smoothstep(0.42, 0.75, length(d));
	hit += (hash12(gl_FragCoord.xy + fract(uTime.x * 0.1234) * 517.0) - 0.5) * uPost.z;
	fragColor = TDOutputSwizzle(vec4(clamp(hit, 0.0, 1.0), 1.0));
	fragTrail = TDOutputSwizzle(vec4(c, 1.0));
}
