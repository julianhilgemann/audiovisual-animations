// glsl_frames_compute: shared by the three glslPOPs of the 3D wavetable scene.
// Each grid is rows x columns of points; Tex.x is the phase along a row, Tex.y picks the row.
// uState.w selects what the calling POP builds:
//   0  history lines   (geo_frames)  one line per history window (sFrames, one texture row each),
//                      2003 at the back (z = -depth) to today at the front; the windows nearest
//                      the scan position light up with the loudness envelope.
//   1  curtains        (geo_terrain) two rows per window -- just under the line and the floor --
//                      forming an opaque black skirt, so ridges hide the lines behind them.
//   2  live cycle      (geo_current) the cycle playing now (sWave, shaped row) at its scan depth,
//                      drawn on top with a spark running along it at the slow-motion playhead.
// Uniforms (Vectors page): uState = scanfrac, amp env, slow phase, mode
//                          uShape = width, amplitude, depth (half), rows of the input grid

void main() {
	const uint id = TDIndex();
	if (id >= TDNumElements())
		return;
	vec3 tex = TDIn_Tex();
	float u = tex.x;
	float rows = uShape.w;
	float row = floor(tex.y * (rows - 1.0) + 0.5);
	float scan = uState.x;
	float amp = uState.y;
	float slow = uState.z;
	float mode = uState.w;
	vec3 pos;
	vec4 col;
	float width = 1.0;
	if (mode > 1.5) {
		float v = texture(sWave, vec2(u + 0.5 / 2048.0, 0.25)).r;
		pos = vec3((u - 0.5) * uShape.x, v * uShape.y, (scan * 2.0 - 1.0) * uShape.z);
		float spark = exp(-pow((fract(u - slow + 0.5) - 0.5) * 20.0, 2.0));
		vec3 hot = mix(vec3(0.75, 1.00, 1.00), vec3(1.00, 0.72, 0.20), spark);
		col = vec4(hot * (0.9 + 1.2 * amp + 2.2 * spark), 1.0);
		width = 2.6 + 4.0 * spark;
	} else {
		float frames = mode > 0.5 ? rows * 0.5 : rows;
		float k = mode > 0.5 ? floor(row * 0.5) : row;
		float f = k / max(frames - 1.0, 1.0);
		float v = texture(sFrames, vec2(u + 0.5 / 256.0, (k + 0.5) / frames)).r;
		float z = (f * 2.0 - 1.0) * uShape.z;
		if (mode > 0.5) {
			float y = mod(row, 2.0) < 0.5 ? v * uShape.y - 0.006 : -1.7 * uShape.y;
			pos = vec3((u - 0.5) * uShape.x, y, z);
			col = vec4(0.012, 0.016, 0.03, 1.0);
		} else {
			pos = vec3((u - 0.5) * uShape.x, v * uShape.y, z);
			float near = exp(-pow((f - scan) * frames / 2.5, 2.0));
			vec3 base = mix(vec3(0.20, 0.45, 1.00), vec3(0.00, 0.95, 1.00), f);
			col = vec4(base * (1.0 + 0.4 * f + near * (1.4 + 1.2 * amp)), 1.0);
			width = 1.2 + 2.2 * near;
		}
	}
	P[id] = pos;
	Color[id] = col;
	LineWidth[id] = width;
}
