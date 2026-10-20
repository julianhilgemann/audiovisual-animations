// glsl_bg: running empty-room background for the silhouette key (camera resolution).
// Input 0: null_cam, the current camera frame.
// Input 1: feedback_bg, the previous background. Capture Background resets that
//          Feedback TOP, which then hands over the camera frame itself.
// Input 2: feedback_presence, the previous presence (R = silhouette mask): covered
//          pixels learn 10x slower, so a visitor standing still fades out slowly.
// A silhouette covering > 80 % of the frame is not a visitor but a stale
// background (camera warm-up, lights switched): then everything re-learns fast.
// The area is estimated here from the previous mask (8 x 5 samples) rather than
// read back from the CPU, which would close a cook loop through glsl_stats.
uniform vec4 uLearn;   // x = blend toward the camera per frame (0 = frozen)

layout(location = 0) out vec4 fragColor;

void main() {
	vec3 cam = texture(sTD2DInputs[0], vUV.st).rgb;
	vec3 bg = texture(sTD2DInputs[1], vUV.st).rgb;
	float mask = texture(sTD2DInputs[2], vUV.st).r;
	float area = 0.0;
	for (int j = 0; j < 5; j++) {
		for (int i = 0; i < 8; i++) {
			area += texture(sTD2DInputs[2], (vec2(float(i), float(j)) + 0.5) / vec2(8.0, 5.0)).r;
		}
	}
	area /= 40.0;
	float rate = uLearn.x * (1.0 - 0.9 * mask);
	if (area > 0.8) {
		rate = max(rate, 0.03);
	}
	fragColor = TDOutputSwizzle(vec4(mix(bg, cam, rate), 1.0));
}
