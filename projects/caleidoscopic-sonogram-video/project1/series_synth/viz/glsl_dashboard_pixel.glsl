// glsl_dashboard: the complete 1920x1080 neon dashboard in one pass.
//
// Inputs (sTD2DInputs):
//   0 chopto_series    rows: t, value_bn (EUR bn) -- one texel per month
//   1 chopto_wave      rows: shaped, raw -- one cycle, 2048 samples
//   2 chopto_scope     the last whole output cycle, 512 samples (script_scope)
//   3 null_specsmooth  R smoothed, G peak hold, B instant (0..1 = -96..0 dB), 0..22050 Hz linear
//   4 null_sono        sonogram: x = time (newest right), y = log f 20 Hz..20 kHz
//   5 scene3d          the rendered 3D wavetable stack (fills the wt3d plot rect 1:1)
//   6 chopto_env       rows: gate, amp env, filter env over the last 4 s
//   7 chopto_harm      rows: shaped_db, raw_db for harmonics 1..64
//   8..12 labels       text layers axis, title, dim, value, header (white, alpha = coverage)
// Panel rectangles come from viz/layout through uRects / uInsets (Arrays page) -- the
// table labels_lib places every label from. All geometry is in 1920x1080 DESIGN units;
// the TOP renders at any 16:9 size (1280x720 under a Non-Commercial licence) and maps
// gl_FragCoord into design units, so lines stay proportionally thick. Other constants shared with labels_lib:
// SCOPE_RANGE, FMIN/FMAX, SONO_SECONDS, ENV_SECONDS and the legend geometry.

uniform vec4 uRects[8];   // x, y, w, h in px, origin bottom-left, layout table order
uniform vec4 uInsets[8];  // plot insets: left, bottom, right, top
uniform vec4 uAxisS;      // series: ymin, ymax, ystep (EUR bn), tmin (year)
uniform vec4 uAxisT;      // series: tmax (year), t of month 0, months, unused
uniform vec4 uWin;        // window start (months), length (months), scan fraction, slow phase 0-1
uniform vec4 uPitch;      // f0 Hz (with glide), harmonics below Nyquist, cutoff now Hz, ping-pong flag
uniform vec4 uEnv;        // gate, amp env, filter env, output rms
uniform vec4 uFilt;       // base cutoff Hz, resonance, roll-off dB/oct, type (0 lp, 1 hp, 2 bp, 3 br)
uniform vec4 uMisc;       // time s (wraps hourly), glow, volume, unused

layout(location = 0) out vec4 fragColor;

float gAA = 0.5;                           // half anti-alias band in design px (set in main)

const vec3 BG      = vec3(0.008, 0.010, 0.020);
const vec3 PANEL   = vec3(0.016, 0.022, 0.042);
const vec3 GRID    = vec3(0.075, 0.105, 0.175);
const vec3 CYAN    = vec3(0.00, 0.90, 1.00);
const vec3 TEAL    = vec3(0.10, 0.42, 0.62);
const vec3 MAGENTA = vec3(1.00, 0.16, 0.72);
const vec3 PINK    = vec3(1.00, 0.62, 0.90);
const vec3 AMBER   = vec3(1.00, 0.64, 0.08);
const vec3 WHITE   = vec3(1.00);
const vec3 LABEL   = vec3(0.50, 0.58, 0.72);
const float FMIN = 20.0;
const float FMAX = 20000.0;
const float NYQUIST = 22050.0;
const float SCOPE_RANGE = 1.15;
const float SONO_SECONDS = 512.0 / 60.0;
const float ENV_SECONDS = 4.0;

// ---- helpers --------------------------------------------------------------------
vec4 plotRect(int i) {
	vec4 r = uRects[i];
	vec4 m = uInsets[i];
	return vec4(r.xy + m.xy, r.zw - m.xy - m.zw);
}
bool inside(vec2 p, vec4 r) {
	return all(greaterThanEqual(p, r.xy)) && all(lessThan(p, r.xy + r.zw));
}
float stroke(float d, float hw) {          // anti-aliased line of half-width hw design px
	return 1.0 - smoothstep(hw - gAA, hw + gAA, d);
}
float halo(float d, float r) {             // soft neon halo, scaled by the Glow parameter
	return exp(-d * d / (2.0 * r * r)) * uMisc.y;
}
float gridDist(float v, float step, float pxPerUnit) {
	return abs(v - step * floor(v / step + 0.5)) * pxPerUnit;
}
float flog(float f) {                       // 20 Hz..20 kHz -> 0..1
	return log(f / FMIN) / log(FMAX / FMIN);
}
float freqAt(float u) {
	return FMIN * pow(FMAX / FMIN, u);
}
float sampleRow(sampler2D s, float u, float row, float rows) {
	float w = float(textureSize(s, 0).x);
	return texture(s, vec2((clamp(u, 0.0, 1.0) * (w - 1.0) + 0.5) / w, (row + 0.5) / rows)).r;
}
// distance (px) from p.y to a curve whose heights (px) are yl, yc, yr at x-1, x, x+1
float curveDist(float py, float yl, float yc, float yr) {
	float lo = min(yc, min(0.5 * (yc + yl), 0.5 * (yc + yr)));
	float hi = max(yc, max(0.5 * (yc + yl), 0.5 * (yc + yr)));
	float slope = 0.5 * (yr - yl);
	float perp = abs(py - yc) / sqrt(1.0 + slope * slope);
	return min(perp, max(max(lo - py, py - hi), 0.0));
}
vec3 accentOf(int i) {
	return (i == 5 || i == 6) ? MAGENTA : (i == 7 ? AMBER : CYAN);
}

// ---- panel frame ----------------------------------------------------------------
vec3 panelChrome(vec2 p, int i) {
	vec4 r = uRects[i];
	vec2 q = p - r.xy;
	vec3 c = PANEL * (0.85 + 0.3 * q.y / r.w);
	float edge = min(min(q.x, r.z - q.x), min(q.y, r.w - q.y));
	c += GRID * 1.4 * stroke(edge, 0.6);
	vec3 acc = accentOf(i);
	float L = 22.0;
	float tl = ((q.x < L && r.w - q.y < 2.0) || (r.w - q.y < L && q.x < 2.0)) ? 1.0 : 0.0;
	float br = ((r.z - q.x < L && q.y < 2.0) || (q.y < L && r.z - q.x < 2.0)) ? 1.0 : 0.0;
	c += acc * (tl + br) * (0.7 + 0.4 * uEnv.y);
	if (i != 0) {                           // fading rule under the title row
		float fade = 1.0 - q.x / r.z;
		c += acc * 0.22 * fade * stroke(abs(q.y - (r.w - 33.0)), 0.5) * step(14.0, q.x);
	}
	return c;
}

// ---- header -------------------------------------------------------------------------
vec3 drawHeader(vec2 p) {
	vec4 r = uRects[0];
	vec2 q = p - r.xy;
	float sweep = exp(-pow((q.x / r.z - uWin.w) * 7.0, 2.0));
	vec3 c = CYAN * stroke(abs(q.y - 1.0), 0.8) * (0.25 + 1.2 * sweep);
	float dl = length(q - vec2(r.z - 22.0, r.w * 0.5));
	c += AMBER * (stroke(dl, 6.0) * (0.2 + 0.9 * uEnv.x) + 0.8 * halo(dl, 10.0) * uEnv.y);
	return c;
}

// ---- source series ----------------------------------------------------------------
float seriesAt(float i) {
	float n = uAxisT.z;
	return texture(sTD2DInputs[0], vec2((clamp(i, 0.0, n - 1.0) + 0.5) / n, 0.75)).r;
}
vec3 drawSeries(vec2 p) {
	vec4 pr = plotRect(1);
	if (!inside(p, pr)) return vec3(0.0);
	vec2 l = (p - pr.xy) / pr.zw;
	float tmin = uAxisS.w, tmax = uAxisT.x, t0 = uAxisT.y, n = uAxisT.z;
	float ymin = uAxisS.x;
	float pxYear = pr.z / (tmax - tmin);
	float pxUnit = pr.w / (uAxisS.y - ymin);
	float t = mix(tmin, tmax, l.x);
	float v = mix(ymin, uAxisS.y, l.y);
	vec3 c = vec3(0.0);
	float yr = floor(t + 0.5);
	c += GRID * stroke(abs(t - yr) * pxYear, 0.5) * (mod(yr, 5.0) < 0.5 ? 1.3 : 0.55);
	c += GRID * 0.8 * stroke(gridDist(v, uAxisS.z, pxUnit), 0.5);
	float i = (t - t0) * 12.0;                  // fractional month under this pixel
	float di = 12.0 / pxYear;                   // months per pixel
	float ws = uWin.x - 0.5, we = uWin.x + uWin.y - 0.5;
	bool inWin = i >= ws && i < we;
	if (inWin) c += CYAN * (0.03 + 0.06 * exp(-min(i - ws, we - i) / di / 26.0));
	c += CYAN * 0.75 * stroke(min(abs(i - ws), abs(i - we)) / di, 0.7);
	if (i < -0.5 || i > n - 0.5) return c;
	float yc = pr.y + (seriesAt(i) - ymin) * pxUnit;
	if (p.y < yc) {
		float a = (p.y - pr.y) / max(yc - pr.y, 1.0);
		c += (inWin ? CYAN * 0.17 : TEAL * 0.07) * a * a;
	}
	float ma = 0.0;                             // 12-month moving average = trend
	for (int k = 0; k < 12; k++) ma += seriesAt(i - 5.5 + float(k));
	c += WHITE * 0.30 * stroke(abs(p.y - (pr.y + (ma / 12.0 - ymin) * pxUnit)), 0.6);
	float d = curveDist(p.y, pr.y + (seriesAt(i - di) - ymin) * pxUnit, yc,
	                    pr.y + (seriesAt(i + di) - ymin) * pxUnit);
	if (inWin) {
		c += CYAN * (0.8 + 0.5 * uEnv.y) * (stroke(d, 1.3) + 0.35 * halo(d, 3.0));
		float im = floor(i + 0.5);
		vec2 dd = vec2((i - im) / di, p.y - (pr.y + (seriesAt(im) - ymin) * pxUnit));
		c += WHITE * 0.85 * stroke(length(dd), 2.2);
	} else {
		c += TEAL * (stroke(d, 0.9) + 0.25 * halo(d, 2.5));
	}
	// playhead: one sweep of the window per slow-motion period (back and forth in ping-pong)
	bool pp = uPitch.w > 0.5;
	float pos = pp ? 1.0 - abs(2.0 * uWin.w - 1.0) : uWin.w;
	float ip = ws + pos * uWin.y;
	float dir = (pp && uWin.w > 0.5) ? -1.0 : 1.0;
	float back = dir * (ip - i) / uWin.y;
	if (inWin && back >= 0.0 && back < 0.22)
		c += AMBER * (1.0 - back / 0.22) * (stroke(d, 1.6) + 0.5 * halo(d, 4.0));
	c += AMBER * 0.35 * stroke(abs(i - ip) / di, 0.6);
	float dHead = length(vec2((i - ip) / di, p.y - (pr.y + (seriesAt(ip) - ymin) * pxUnit)));
	c += AMBER * (stroke(dHead, 4.0) + 0.8 * halo(dHead, 8.0));
	float dLast = length(vec2((i - (n - 1.0)) / di, p.y - (pr.y + (seriesAt(n - 1.0) - ymin) * pxUnit)));
	c += WHITE * (stroke(dLast, 3.0) + 0.5 * (0.5 + 0.5 * sin(uMisc.x * 3.0)) * halo(dLast, 9.0));
	return c;
}

// ---- statistics ---------------------------------------------------------------------
vec3 drawStats(vec2 p) {
	vec4 r = uRects[2];
	vec2 q = p - r.xy;
	vec3 c = vec3(0.0);
	c += GRID * 1.2 * stroke(abs(q.x - r.z * 0.5), 0.5) * step(24.0, q.y) * step(q.y, r.w - 40.0);
	float row = floor((r.w - 48.0 - q.y) / 19.0 + 0.5);   // labels_lib STATS_TOP / STATS_PITCH
	if (row >= 0.0 && row < 12.0 && mod(row, 2.0) < 0.5 && q.x > 8.0 && q.x < r.z - 8.0)
		c += vec3(0.010, 0.014, 0.028);
	float db = 20.0 * log(max(uEnv.w, 1e-6)) / log(10.0);
	float lvl = clamp((db + 60.0) / 60.0, 0.0, 1.0);       // meter: -60..0 dBFS, 48 segments
	vec4 m = vec4(16.0, 8.0, r.z - 32.0, 7.0);
	if (q.x > m.x && q.x < m.x + m.z && q.y > m.y && q.y < m.y + m.w) {
		float u = (q.x - m.x) / m.z;
		vec3 sc = u < 0.8 ? CYAN : (u < 0.93 ? AMBER : MAGENTA);
		c += sc * step(0.22, fract(u * 48.0)) * (u < lvl ? 1.0 : 0.10);
	}
	return c;
}

// ---- oscillator -----------------------------------------------------------------------
float wave(float row, float ph) {
	return sampleRow(sTD2DInputs[1], fract(ph), row, 2.0);
}
vec3 drawScope(vec2 p) {
	vec4 pr = plotRect(3);
	if (!inside(p, pr)) return vec3(0.0);
	vec2 l = (p - pr.xy) / pr.zw;
	float pxUnit = pr.w / (2.0 * SCOPE_RANGE);
	float pxCycle = pr.z;                       // one cycle across the plot
	float v = mix(-SCOPE_RANGE, SCOPE_RANGE, l.y);
	float ph = l.x;
	vec3 c = vec3(0.0);
	c += GRID * 0.7 * stroke(gridDist(v, 0.5, pxUnit), 0.5);
	c += GRID * 1.3 * stroke(abs(v) * pxUnit, 0.6);
	c += GRID * 0.55 * stroke(gridDist(ph, 0.125, pxCycle), 0.5);
	c += GRID * 1.2 * stroke(gridDist(ph, 0.5, pxCycle), 0.6);
	float dph = 1.0 / pxCycle;
	float y0 = pr.y + SCOPE_RANGE * pxUnit;
	float dRaw = curveDist(p.y, y0 + wave(1.0, ph - dph) * pxUnit, y0 + wave(1.0, ph) * pxUnit,
	                       y0 + wave(1.0, ph + dph) * pxUnit);
	c += TEAL * 0.95 * stroke(dRaw, 0.9);
	float dShaped = curveDist(p.y, y0 + wave(0.0, ph - dph) * pxUnit, y0 + wave(0.0, ph) * pxUnit,
	                          y0 + wave(0.0, ph + dph) * pxUnit);
	c += CYAN * (stroke(dShaped, 1.3) + 0.15 * halo(dShaped, 3.0));
	float g = 1.0 / max(uMisc.z, 0.05);        // show the output at unit volume
	float du = 1.0 / pr.z;
	float dOut = curveDist(p.y, y0 + sampleRow(sTD2DInputs[2], l.x - du, 0.0, 1.0) * g * pxUnit,
	                       y0 + sampleRow(sTD2DInputs[2], l.x, 0.0, 1.0) * g * pxUnit,
	                       y0 + sampleRow(sTD2DInputs[2], l.x + du, 0.0, 1.0) * g * pxUnit);
	c += WHITE * (0.45 + 0.65 * uEnv.y) * (stroke(dOut, 1.1) + 0.2 * halo(dOut, 3.5));
	vec2 dotP = vec2(pr.x + uWin.w * pxCycle, y0 + wave(0.0, uWin.w) * pxUnit);
	float dd = length(p - dotP);
	c += AMBER * (stroke(dd, 4.0) + 0.9 * halo(dd, 9.0));
	c += AMBER * 0.25 * stroke(abs(p.x - dotP.x), 0.5);
	return c;
}

// ---- 3D wavetable -----------------------------------------------------------------------
vec3 draw3D(vec2 p) {
	vec4 pr = plotRect(4);
	if (!inside(p, pr)) return vec3(0.0);
	vec2 l = (p - pr.xy) / pr.zw;
	vec3 c = texture(sTD2DInputs[5], l).rgb;
	// history bar along the bottom: where the playing window sits in 2003 .. today
	float dy = abs(p.y - (pr.y + 4.0));
	c += GRID * 1.5 * stroke(dy, 1.0);
	c += CYAN * 0.8 * stroke(dy, 1.0) * step(l.x, uWin.z);
	float dm = length(vec2(p.x - (pr.x + uWin.z * pr.z), dy));
	c += AMBER * (stroke(dm, 3.5) + 0.7 * halo(dm, 7.0));
	return c;
}

// ---- spectrum -----------------------------------------------------------------------------
vec4 specAt(float f) {
	float w = float(textureSize(sTD2DInputs[3], 0).x);
	return texture(sTD2DInputs[3], vec2((clamp(f / NYQUIST, 0.0, 1.0) * (w - 1.0) + 0.5) / w, 0.5));
}
vec3 drawSpectrum(vec2 p) {
	vec4 pr = plotRect(5);
	if (!inside(p, pr)) return vec3(0.0);
	vec2 l = (p - pr.xy) / pr.zw;
	float f = freqAt(l.x);
	vec3 c = vec3(0.0);
	for (int k = 0; k < 4; k++) {               // 1-2-5 grid per decade
		for (int m = 0; m < 3; m++) {
			float fl = 10.0 * pow(10.0, float(k)) * (m == 0 ? 1.0 : (m == 1 ? 2.0 : 5.0));
			if (fl < FMIN || fl > FMAX) continue;
			c += GRID * (m == 0 ? 1.3 : 0.55) * stroke(abs(p.x - (pr.x + flog(fl) * pr.z)), 0.5);
		}
	}
	c += GRID * 0.8 * stroke(gridDist(l.y * 96.0, 12.0, pr.w / 96.0), 0.5);
	// harmonics of the table itself (before the filter) as ghost bars at k * f0
	float hk = floor(f / max(uPitch.x, 1.0) + 0.5);
	if (hk >= 1.0 && hk <= min(64.0, max(uPitch.y, 1.0))) {
		float xk = pr.x + flog(hk * uPitch.x) * pr.z;
		float db = sampleRow(sTD2DInputs[7], (hk - 1.0) / 63.0, 0.0, 2.0);
		if (p.y < pr.y + clamp((db + 96.0) / 96.0, 0.0, 1.0) * pr.w)
			c += MAGENTA * 0.20 * stroke(abs(p.x - xk), 1.2);
		if (p.y < pr.y + 6.0)
			c += AMBER * (hk == 1.0 ? 0.9 : 0.35) * stroke(abs(p.x - xk), 0.8);
	}
	// filter response (dashed amber) following the filter envelope
	float fc = max(uPitch.z, 1.0);
	float poles = uFilt.z / 6.0;
	float r = f / fc;
	float lp = 1.0 / sqrt(1.0 + pow(r, 2.0 * poles));
	float hp = 1.0 / sqrt(1.0 + pow(1.0 / r, 2.0 * poles));
	float resp = uFilt.w < 0.5 ? lp : (uFilt.w < 1.5 ? hp : (uFilt.w < 2.5 ? min(2.0 * lp * hp, 1.0) : 1.0 - min(2.0 * lp * hp, 1.0)));
	resp *= 1.0 + 2.5 * uFilt.y * exp(-pow(log2(r) * 3.0, 2.0));
	float yResp = pr.y + clamp((20.0 * log(max(resp, 1e-5)) / log(10.0) + 96.0) / 96.0, 0.0, 1.0) * pr.w;
	c += AMBER * 0.75 * step(0.45, fract(p.x / 9.0)) * stroke(abs(p.y - yResp), 0.8);
	float dc = abs(p.x - (pr.x + flog(clamp(fc, FMIN, FMAX)) * pr.z));
	c += AMBER * (0.55 * stroke(dc, 0.7) + 0.5 * halo(dc, 4.0) * uEnv.z);
	// live spectrum: gradient fill, neon line, peak hold
	float du = 1.0 / pr.z;
	vec4 s = specAt(f);
	float ys = pr.y + s.r * pr.w;
	if (p.y < ys) {
		float a = (p.y - pr.y) / pr.w;
		c += MAGENTA * (0.06 + 0.30 * a * a);
	}
	float d = curveDist(p.y, pr.y + specAt(freqAt(l.x - du)).r * pr.w, ys, pr.y + specAt(freqAt(l.x + du)).r * pr.w);
	c += MAGENTA * (stroke(d, 1.2) + 0.4 * halo(d, 3.5));
	c += PINK * 0.55 * stroke(abs(p.y - (pr.y + s.g * pr.w)), 0.6);
	return c;
}

// ---- sonogram -------------------------------------------------------------------------------
vec3 neonMap(float x) {
	x = clamp(x, 0.0, 1.0);
	vec3 c = mix(vec3(0.0), vec3(0.04, 0.03, 0.30), smoothstep(0.0, 0.3, x));
	c = mix(c, vec3(0.50, 0.05, 0.75), smoothstep(0.25, 0.5, x));
	c = mix(c, MAGENTA, smoothstep(0.45, 0.65, x));
	c = mix(c, AMBER, smoothstep(0.62, 0.84, x));
	return mix(c, vec3(1.0, 0.95, 0.8), smoothstep(0.84, 1.0, x));
}
vec3 drawSonogram(vec2 p) {
	vec4 pr = plotRect(6);
	if (!inside(p, pr)) return vec3(0.0);
	vec2 l = (p - pr.xy) / pr.zw;
	vec3 c = neonMap((texture(sTD2DInputs[4], l).r - 0.30) / 0.62) * 1.1;
	for (int k = 0; k < 3; k++) {
		float fy = pr.y + flog(100.0 * pow(10.0, float(k))) * pr.w;
		c += GRID * 1.2 * stroke(abs(p.y - fy), 0.5);
	}
	c += GRID * 0.9 * stroke(gridDist((1.0 - l.x) * SONO_SECONDS, 1.0, pr.z / SONO_SECONDS), 0.5);
	float yc = pr.y + flog(clamp(uPitch.z, FMIN, FMAX)) * pr.w;   // filter cutoff now
	if (p.x > pr.x + pr.z - 12.0) c += AMBER * stroke(abs(p.y - yc), 1.2);
	return c;
}

// ---- envelopes -------------------------------------------------------------------------------
float envAt(float row, float u) {
	return sampleRow(sTD2DInputs[6], u, row, 3.0);
}
vec3 drawEnv(vec2 p) {
	vec4 pr = plotRect(7);
	if (!inside(p, pr)) return vec3(0.0);
	vec2 l = (p - pr.xy) / pr.zw;
	float du = 1.0 / pr.z;
	vec3 c = vec3(0.0);
	c += GRID * 0.8 * stroke(gridDist(l.y, 0.5, pr.w), 0.5);
	c += GRID * 0.6 * stroke(gridDist(l.x * ENV_SECONDS, 1.0, pr.z / ENV_SECONDS), 0.5);
	float gate = step(0.5, envAt(0.0, l.x));
	c += WHITE * 0.03 * gate;
	if (p.y < pr.y + 5.0) c += WHITE * 0.45 * gate;
	float ya = pr.y + envAt(1.0, l.x) * pr.w;
	if (p.y < ya) c += AMBER * 0.16 * (p.y - pr.y) / pr.w;
	float da = curveDist(p.y, pr.y + envAt(1.0, l.x - du) * pr.w, ya, pr.y + envAt(1.0, l.x + du) * pr.w);
	c += AMBER * (stroke(da, 1.2) + 0.35 * halo(da, 3.0));
	float yf = pr.y + envAt(2.0, l.x) * pr.w;
	float df = curveDist(p.y, pr.y + envAt(2.0, l.x - du) * pr.w, yf, pr.y + envAt(2.0, l.x + du) * pr.w);
	c += MAGENTA * (stroke(df, 1.0) + 0.3 * halo(df, 3.0));
	float dA = length(p - vec2(pr.x + pr.z - 3.0, pr.y + uEnv.y * pr.w));
	c += AMBER * (stroke(dA, 3.5) + 0.7 * halo(dA, 7.0));
	float dF = length(p - vec2(pr.x + pr.z - 3.0, pr.y + uEnv.z * pr.w));
	c += MAGENTA * (stroke(dF, 3.0) + 0.6 * halo(dF, 6.0));
	return c;
}

// ---- legends (geometry mirrors labels_lib LEGEND_*) -----------------------------------------------
float legendSwatch(vec2 p, vec4 pr, bool right, int i) {
	float yc = pr.y + pr.w - 12.0 - 16.0 * float(i);
	float xs = right ? pr.x + pr.z - 150.0 : pr.x + 10.0;
	return (p.x > xs && p.x < xs + 18.0) ? stroke(abs(p.y - yc), 1.0) : 0.0;
}
float legendBox(vec2 p, vec4 pr, bool right, int n, float width) {
	float xs = right ? pr.x + pr.z - 156.0 : pr.x + 4.0;
	float y1 = pr.y + pr.w - 3.0;
	float y0 = y1 - 16.0 * float(n) - 2.0;
	return (p.x > xs && p.x < xs + width && p.y > y0 && p.y < y1) ? 1.0 : 0.0;
}
vec3 drawLegends(vec2 p, int panel, vec3 col) {
	if (panel == 3) {
		vec4 pr = plotRect(3);
		col = mix(col, PANEL, 0.8 * legendBox(p, pr, false, 4, 152.0));
		col += TEAL * legendSwatch(p, pr, false, 0) + CYAN * legendSwatch(p, pr, false, 1)
		     + WHITE * legendSwatch(p, pr, false, 2) + AMBER * legendSwatch(p, pr, false, 3);
	} else if (panel == 5) {
		vec4 pr = plotRect(5);
		col = mix(col, PANEL, 0.8 * legendBox(p, pr, true, 4, 152.0));
		col += MAGENTA * legendSwatch(p, pr, true, 0) + PINK * 0.7 * legendSwatch(p, pr, true, 1)
		     + MAGENTA * 0.35 * legendSwatch(p, pr, true, 2) + AMBER * legendSwatch(p, pr, true, 3);
	} else if (panel == 7) {
		// side column right of the plot: swatches on rows 0 (gate), 1 (amp), 4 (filter);
		// labels_lib writes the live ADSR values on the rows between them
		vec4 pr = plotRect(7);
		vec4 side = vec4(pr.x + pr.z + 14.0 - 10.0, pr.y, 0.0, pr.w);
		col += WHITE * 0.5 * legendSwatch(p, side, false, 0) + AMBER * legendSwatch(p, side, false, 1)
		     + MAGENTA * legendSwatch(p, side, false, 4);
	}
	return col;
}

// ---- text layers ---------------------------------------------------------------------------------
vec3 applyText(ivec2 px, int panel, vec3 col) {
	vec3 acc = panel >= 0 ? accentOf(panel) : CYAN;
	col = mix(col, LABEL * 0.95, texelFetch(sTD2DInputs[8], px, 0).a);
	col = mix(col, LABEL * 0.85, texelFetch(sTD2DInputs[10], px, 0).a);
	col = mix(col, mix(WHITE, acc, 0.15), texelFetch(sTD2DInputs[11], px, 0).a);
	col = mix(col, acc * 1.05 + 0.10, texelFetch(sTD2DInputs[9], px, 0).a);
	col = mix(col, WHITE * 1.1, texelFetch(sTD2DInputs[12], px, 0).a);
	return col;
}

void main() {
	float design = 1920.0 / uTDOutputInfo.res.z;   // design px per output px
	gAA = 0.5 * design;
	vec2 p = gl_FragCoord.xy * design;
	vec2 v = (vUV.st - 0.5) * vec2(1.0, 0.8);
	vec3 col = BG * (1.0 - 1.6 * dot(v, v));
	int panel = -1;
	for (int i = 0; i < 8; i++) {
		if (inside(p, uRects[i])) panel = i;
	}
	if (panel >= 0) {
		col = panelChrome(p, panel);
		if (panel == 0) col += drawHeader(p);
		else if (panel == 1) col += drawSeries(p);
		else if (panel == 2) col += drawStats(p);
		else if (panel == 3) col += drawScope(p);
		else if (panel == 4) col += draw3D(p);
		else if (panel == 5) col += drawSpectrum(p);
		else if (panel == 6) col += drawSonogram(p);
		else col += drawEnv(p);
		col = drawLegends(p, panel, col);
	}
	col = applyText(ivec2(gl_FragCoord.xy), panel, col);
	fragColor = TDOutputSwizzle(vec4(col, 1.0));
}
