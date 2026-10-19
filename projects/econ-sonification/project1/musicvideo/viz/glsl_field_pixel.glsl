// glsl_field: one texel per point of the cloud = the instancing data of geo_cloud.
// Output W x (H * LAYERS) texels; layer = row / H (three stacked sheets / shells).
// Buffer 0 (this TOP -> null_field):         xyz = world position, w = dot radius (world units)
// Buffer 1 (renderselect_color -> null_color): rgb = dot colour (intensity folded in), a = 1
// Input 0: null_history     ring buffer: R smoothed track level, G instant level, B waveform (-1..1)
// Input 1: select_presence  modulator video: R mask, G motion trail (NOT mirrored here)
//
// Every point owns an (age, content) pair: age 0 = newest moment, content = log frequency.
// Forms lay that pair out in space (and Morph blends sheet -> form with the SAME pairs):
//   0 sheet  : age across the screen (Flow Direction), content across the other axis
//   1 tunnel : age = depth (newest far away, flowing at the camera), content = angle
//   2 disc   : age = angle (the record turns as the history flows), content = radius
// Symmetry mirrors the content axis N times. The video is projected from the camera onto the
// form: its mask pushes points toward the camera (Video Displace) and lights them.
uniform vec4 uFlow;    // x head column, y direction (0 left, 1 right, 2 up, 3 down), z mirror 0/1, w breath phase 0-1
uniform vec4 uShape;   // x Waveform Depth, y Thickness, z Scatter, w Point Size
uniform vec4 uReact;   // x Video Displace, y Video Imprint, z Motion Ripple, w Video in Points
uniform vec4 uNoise;   // x low, y mid, z high, w transient (each already x its amount x Chaos)
uniform vec4 uPal;     // x palette index, y scale offset, z contrast (gamma), w transient layer
uniform vec4 uMisc;    // x frame counter (jitter seed), y tan(fov / 2), z field half-size, w aspect
uniform vec4 uForm;    // x form (0 sheet, 1 tunnel, 2 disc), y morph 0-1, z twist (turns), w low pump
uniform vec4 uForm2;   // x symmetry N, y tunnel length, z warp amount, w camera distance

#define LAYERS 3
#define TAU 6.2831853

layout(location = 0) out vec4 fragPos;
layout(location = 1) out vec4 fragCol;

vec3 hash3(vec2 p) {
	vec3 q = vec3(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)), dot(p, vec2(419.2, 371.9)));
	return fract(sin(q) * 43758.5453) * 2.0 - 1.0;
}

// 6th-order fits of the matplotlib scales (Matt Zucker, CC0) and Turbo (Google).
vec3 poly6(float t, vec3 c0, vec3 c1, vec3 c2, vec3 c3, vec3 c4, vec3 c5, vec3 c6) {
	return c0 + t * (c1 + t * (c2 + t * (c3 + t * (c4 + t * (c5 + t * c6)))));
}

vec3 palette(int idx, float t) {
	t = clamp(t, 0.0, 1.0);
	if (idx == 0) {          // inferno
		return poly6(t, vec3(0.0002189403691192265, 0.001651004631001012, -0.01948089843709184),
			vec3(0.1065134194856116, 0.5639564367884091, 3.932712388889277),
			vec3(11.60249308247187, -3.972853965665698, -15.9423941062914),
			vec3(-41.70399613139459, 17.43639888205313, 44.35414519872813),
			vec3(77.162935699427, -33.40235894210092, -81.80730925738993),
			vec3(-71.31942824499214, 32.62606426397723, 73.20951985803202),
			vec3(25.13112622477341, -12.24266895238567, -23.07032500287172));
	} else if (idx == 1) {   // magma
		return poly6(t, vec3(-0.002136485053939582, -0.000749655052795221, -0.005386127855323933),
			vec3(0.2516605407371642, 0.6775232436837668, 2.494026599312351),
			vec3(8.353717279216625, -3.577719514958484, 0.3144679030132573),
			vec3(-27.66873308576866, 14.26473078096533, -13.64921318813922),
			vec3(52.17613981234068, -27.94360607168351, 12.94416944238394),
			vec3(-50.76852536473588, 29.04658282127291, 4.23415299384598),
			vec3(18.65570506591883, -11.48977351997711, -5.601961508734096));
	} else if (idx == 2) {   // viridis
		return poly6(t, vec3(0.2777273272234177, 0.005407344544966578, 0.3340998053353061),
			vec3(0.1050930431085774, 1.404613529898575, 1.384590162594685),
			vec3(-0.3308618287255563, 0.214847559468213, 0.09509516302823659),
			vec3(-4.634230498983486, -5.799100973351585, -19.33244095627987),
			vec3(6.228269936347081, 14.17993336680509, 56.69055260068105),
			vec3(4.776384997670288, -13.74514537774601, -65.35303263337234),
			vec3(-5.435455855934631, 4.645852612178535, 26.3124352495832));
	} else if (idx == 3) {   // turbo
		vec4 v4 = vec4(1.0, t, t * t, t * t * t);
		vec2 v2 = v4.zw * v4.z;
		return vec3(
			dot(v4, vec4(0.13572138, 4.61539260, -42.66032258, 132.13108234)) + dot(v2, vec2(-152.94239396, 59.28637943)),
			dot(v4, vec4(0.09140261, 2.19418839, 4.84296658, -14.18503333)) + dot(v2, vec2(4.27729857, 2.82956604)),
			dot(v4, vec4(0.10667330, 12.64194608, -60.58204836, 110.36276771)) + dot(v2, vec2(-89.90310912, 27.34824973)));
	} else if (idx == 4) {   // ice: ink blue -> teal -> cyan -> white
		vec3 a = mix(vec3(0.01, 0.02, 0.07), vec3(0.02, 0.30, 0.45), smoothstep(0.0, 0.45, t));
		a = mix(a, vec3(0.35, 0.82, 0.95), smoothstep(0.4, 0.8, t));
		return mix(a, vec3(0.96, 1.0, 1.0), smoothstep(0.78, 1.0, t));
	} else if (idx == 6) {   // steel: neutral, a breath cooler in the shadows
		return vec3(t) * mix(vec3(0.90, 0.95, 1.0), vec3(1.0), t);
	} else if (idx == 7) {   // signal: white, one red accent on the loudest peaks
		return mix(vec3(t), vec3(1.0, 0.06, 0.04) * 1.15, smoothstep(0.84, 0.97, t));
	}
	return vec3(t) * vec3(1.0, 0.97, 0.92);   // mono, warm white
}

// ring-buffer read: linear in time (wrapping) and content, never past the head
vec4 history(float col, float v) {
	ivec2 hres = textureSize(sTD2DInputs[0], 0);
	float n = float(hres.x);
	float c0 = floor(col);
	float f = col - c0;
	float row = clamp(v, 0.0, 1.0) * float(hres.y - 1);
	float r0 = floor(row);
	float g = row - r0;
	int x0 = int(mod(c0, n));
	int x1 = int(mod(c0 + 1.0, n));
	int y0 = int(r0);
	int y1 = min(y0 + 1, hres.y - 1);
	vec4 a = mix(texelFetch(sTD2DInputs[0], ivec2(x0, y0), 0), texelFetch(sTD2DInputs[0], ivec2(x1, y0), 0), f);
	vec4 b = mix(texelFetch(sTD2DInputs[0], ivec2(x0, y1), 0), texelFetch(sTD2DInputs[0], ivec2(x1, y1), 0), f);
	return mix(a, b, g);
}

// mirror the content axis N times (1 = unchanged)
float fold(float c, float n) {
	if (n < 1.5) {
		return c;
	}
	float t = c * n;
	float k = floor(t);
	float f = t - k;
	return mod(k, 2.0) < 0.5 ? f : 1.0 - f;
}

void main() {
	ivec2 px = ivec2(gl_FragCoord.xy);
	ivec2 res = ivec2(uTDOutputInfo.res.zw);
	int rows = res.y / LAYERS;
	int layer = min(px.y / rows, LAYERS - 1);
	float lay = float(layer) - 1.0;                 // -1, 0, 1
	int j = px.y - layer * rows;
	vec2 cell = vec2(1.0 / float(res.x), 1.0 / float(rows));
	vec3 rnd = hash3(vec2(px));              // fixed per point
	vec3 rnd2 = hash3(vec2(px) + 17.31);
	float low = uNoise.x;
	float mid = uNoise.y;
	float high = uNoise.z;
	float kick = uNoise.w;
	int form = int(uForm.x + 0.5);

	// grid position with a fixed scatter, loosened by the mid band
	vec2 uv = (vec2(float(px.x), float(j)) + 0.5) * cell;
	uv += rnd.xy * cell * (uShape.z + 1.0 * mid);

	// (age, content) from the sheet's flow direction; the other forms reuse the same pair
	int dir = int(uFlow.y + 0.5);
	float age;
	float content;
	if (dir == 0) { age = 1.0 - uv.x; content = uv.y; }
	else if (dir == 1) { age = uv.x; content = uv.y; }
	else if (dir == 2) { age = uv.y; content = uv.x; }
	else { age = 1.0 - uv.y; content = uv.x; }
	age = clamp(age + float(layer) * 0.012, 0.0, 1.0);      // deeper sheets = slightly older echoes
	ivec2 hres = textureSize(sTD2DInputs[0], 0);
	vec4 h = history((uFlow.x - 1.0) - age * (float(hres.x) - 4.0), fold(content, uForm2.x));

	// sound level of this point (top 48 dB of the 96 dB scale, through the contrast curve)
	float level = max(h.r, h.g * uPal.w);
	level = clamp((level - 0.5) / 0.5, 0.0, 1.0);
	level = pow(level, uPal.z);
	float pump = uForm.w;

	// ---- sheet
	float S = uMisc.z;
	vec3 ps = vec3((uv.x - 0.5) * 2.0 * uMisc.w * S, (uv.y - 0.5) * 2.0 * S, 0.0);
	vec2 e = abs(uv - 0.5) * 2.0;
	ps.z -= 0.7 * e.x * e.x + 0.35 * e.y * e.y;                    // shallow bowl: the edges recede
	ps.z += uShape.x * 0.7 * h.b * (1.0 + 0.8 * low);             // waveform -> depth, low band pumps it
	ps.z += lay * uShape.y * 0.3;                                  // three sheets
	ps.z += pump * 0.5 * level;                                    // loud bins come forward on the low band

	// ---- chosen form
	vec3 pf = ps;
	if (form == 1) {          // tunnel: newest far away, flowing past the camera
		float th = TAU * (content + uForm.z * age) + lay * 0.07;
		float r = 1.45 * (1.0 + 0.3 * pump) + uShape.x * 0.35 * h.b + lay * uShape.y * 0.22 - 0.35 * level;
		float z = mix(-uForm2.y, 5.0, age);
		pf = vec3(r * cos(th), r * sin(th), z);
	} else if (form == 2) {   // disc: the history turns like a record, low frequencies inside
		float th = TAU * (age + uForm.z * 0.15 * content);
		float r = S * 1.2 * mix(0.22, 1.0, content);
		float z = lay * uShape.y * 0.3 + uShape.x * 0.5 * h.b * (1.0 + 0.8 * low) + pump * 0.6 * level;
		pf = vec3(r * cos(th), r * sin(th), z);
	}
	vec3 p = mix(ps, pf, form == 0 ? 0.0 : clamp(uForm.y, 0.0, 1.0));

	// ---- the video, projected from the camera onto the form
	float depth = max(0.3, uForm2.w - p.z);
	vec2 vuv = 0.5 + p.xy / (2.0 * depth * uMisc.y);
	vec4 cam = texture(sTD2DInputs[1], vec2(uFlow.z > 0.5 ? 1.0 - vuv.x : vuv.x, vuv.y));
	float inside = step(0.0, vuv.x) * step(vuv.x, 1.0) * step(0.0, vuv.y) * step(vuv.y, 1.0);
	float mask = cam.r * inside;
	float motion = cam.g * inside;

	// ---- motion: breathing warp, video emboss, motion ripple, jitter, transient shock
	float ang = TAU * uFlow.w;                                     // idle breathing, loops seamlessly
	vec4 nq = vec4(p.xy * 0.45 + p.z * 0.11, cos(ang) * 0.8, sin(ang) * 0.8);
	p.z += 0.12 * uForm2.z * TDSimplexNoise(nq);
	p.xy += 0.05 * uForm2.z * vec2(TDSimplexNoise(nq + 11.0), TDSimplexNoise(nq + 23.0));
	vec3 toCam = normalize(vec3(0.0, 0.0, uForm2.w) - p);
	p += toCam * uReact.x * mask * 0.6 * (1.0 + 0.25 * rnd2.z);    // the video embossed toward the camera
	vec4 mq = vec4(p.xy * 2.2, cos(ang * 3.0), sin(ang * 3.0));
	p += uReact.z * motion * 0.25 * vec3(TDSimplexNoise(mq), TDSimplexNoise(mq + 5.2), TDSimplexNoise(mq + 9.7));
	vec3 jit = hash3(vec2(px) + fract(uMisc.x * 0.618) * 113.0);  // new every frame
	p += jit * high * 0.07;
	p.xy += normalize(p.xy + 1e-4) * kick * 0.35 * (0.5 + 0.5 * rnd2.x);
	p.z += kick * 0.6 * rnd2.y * (form == 1 ? 0.0 : 1.0);

	// ---- colour and size
	float lv = clamp(level + uPal.y + uReact.y * mask * 0.25, 0.0, 1.0);
	vec3 rgb = palette(int(uPal.x + 0.5), mix(0.06, 1.0, lv));
	float intensity = mix(0.2, 0.9, lv) * (1.0 + 0.6 * motion * uReact.z);
	intensity *= mix(1.0, 0.1 + 1.6 * mask, uReact.w);
	// forms differ in on-screen density: the tunnel spreads its points, the disc packs them
	intensity *= mix(1.1, form == 1 ? 1.5 : (form == 2 ? 0.6 : 1.1), form == 0 ? 0.0 : clamp(uForm.y, 0.0, 1.0));
	float size = uShape.w * 0.0065 * (0.6 + 0.9 * lv) * (1.0 + uReact.y * mask * 0.4) * (1.0 + 0.6 * low);

	fragPos = TDOutputSwizzle(vec4(p, size));
	fragCol = TDOutputSwizzle(vec4(rgb * intensity, 1.0));
}
