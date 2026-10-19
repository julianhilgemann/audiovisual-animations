// glsl_stats: a one-pixel summary of null_presence for the CPU (topto_stats).
// Samples a 40 x 24 grid (constant-bounded loop).
// Out: R = silhouette area as a fraction of the frame,
//      G / B = mask-weighted mean x / y (0.5 when nobody is there),
//      A = mean motion trail.
layout(location = 0) out vec4 fragColor;

void main() {
	float area = 0.0;
	float mx = 0.0;
	float my = 0.0;
	float motion = 0.0;
	for (int j = 0; j < 24; j++) {
		for (int i = 0; i < 40; i++) {
			vec2 uv = (vec2(float(i), float(j)) + 0.5) / vec2(40.0, 24.0);
			vec4 p = texture(sTD2DInputs[0], uv);
			area += p.r;
			mx += p.r * uv.x;
			my += p.r * uv.y;
			motion += p.g;
		}
	}
	float n = 40.0 * 24.0;
	vec2 c = area > 0.5 ? vec2(mx, my) / area : vec2(0.5);
	fragColor = TDOutputSwizzle(vec4(area / n, c, motion / n));
}
