// glsl_post: clarity <-> market noise, then the finish.
// Input 0: bloom_cloud (sharp render + bloom), Input 1: blur_defocus (its blur).
// Mid band -> defocus mix, transients -> colour split, high band -> grain;
// then exposure, filmic (ACES approx) tone map and a soft vignette.
uniform vec4 uPost;   // x defocus 0-1, y colour split, z grain amount, w exposure
uniform vec4 uTime;   // x frame counter (grain seed)

layout(location = 0) out vec4 fragColor;

float hash12(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
	vec2 uv = vUV.st;
	vec2 d = uv - 0.5;
	vec2 off = d * uPost.y * 0.03;
	vec3 sharp = vec3(texture(sTD2DInputs[0], uv + off).r, texture(sTD2DInputs[0], uv).g, texture(sTD2DInputs[0], uv - off).b);
	vec3 soft = vec3(texture(sTD2DInputs[1], uv + off * 1.5).r, texture(sTD2DInputs[1], uv).g, texture(sTD2DInputs[1], uv - off * 1.5).b);
	vec3 c = mix(sharp, soft, clamp(uPost.x, 0.0, 1.0)) + soft * 0.12;
	c *= uPost.w;
	c = (c * (2.51 * c + 0.03)) / (c * (2.43 * c + 0.59) + 0.14);
	c *= 1.0 - 0.35 * smoothstep(0.35, 0.95, length(d * vec2(1.6, 1.0)));
	c += (hash12(gl_FragCoord.xy + fract(uTime.x * 0.1234) * 517.0) - 0.5) * uPost.z;
	fragColor = TDOutputSwizzle(vec4(clamp(c, 0.0, 1.0), 1.0));
}
