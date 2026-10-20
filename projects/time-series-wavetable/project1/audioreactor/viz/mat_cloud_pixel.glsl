// mat_cloud pixel: soft round dot (bright core + faint halo). The MAT blends
// additively (one / one, no depth write), so dense regions read as light.
in Vertex {
	vec4 color;
	vec2 corner;
	flat int cameraIndex;
} iVert;

layout(location = 0) out vec4 oFragColor[TD_NUM_COLOR_BUFFERS];

void main() {
	TDCheckDiscard();
	float r2 = dot(iVert.corner, iVert.corner);
	if (r2 > 1.0) {
		discard;
	}
	float shape = exp(-r2 * 6.0) + (1.0 - r2) * 0.25;
	vec4 c = vec4(iVert.color.rgb * shape, 1.0);
	for (int i = 0; i < TD_NUM_COLOR_BUFFERS; i++) {
		oFragColor[i] = TDOutputSwizzle(c);
	}
}
