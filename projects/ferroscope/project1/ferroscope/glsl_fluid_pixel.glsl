// Ferrofluid height field. A lattice of spikes (hexagonal or square, with optional honeycomb
// ridges and a finer nested lattice) stands in a liquid pool; each spike takes its height and
// colour from the kaleidoscope-folded sonogram at its centre. The surface is warped like a
// liquid; the viewer's presence field raises, leans and lenses it toward the viewer; the
// camera picture can colour it, protrude from it, or draw itself in spikes.
// Output: rgb = fluid colour (linear), a = height (0 = flat pool, ~1 = full spike).
// Inputs: 0 sonogram (R loudness, G onset; x = frequency, y = time, top = newest),
// 1 presence field (A), 2 sonogram blurred (pool), 3 camera picture, 4 previous output (viscosity).

uniform vec4 uKal;     // x mode (0 off, 1 mirror, 2 radial, 3 triangle, 4 square, 5 hex cells, 6 fractal, 7 spiral), y segments, z spin (rad), w twist
uniform vec4 uKal2;    // x radial pinch, y rings, z ring rotation (rad), w sway (rad)
uniform vec4 uKal3;    // x/y centre offset, z tile size, w tile time offset
uniform vec4 uFrac;    // x fold iterations, y fold scale, z fold angle (rad), w fold offset
uniform vec4 uView;    // x zoom, y cells across, z grid (0 hex, 1 square), w grid amount
uniform vec4 uSpike;   // x idle level, y wobble, z sharpness, w spike width
uniform vec4 uShape;   // x spike shape (0 cone, 1 hex pyramid, 2 dome, 3 ring), y structure (0 spikes, 1 honeycomb, 2 both), z ridge width, w grid rotation (rad)
uniform vec4 uShape2;  // x cell randomness, y sub-grid amount, z sub-grid density, w surface tension
uniform vec4 uShape3;  // x spike height, y viscosity, z ripples, w ripple density
uniform vec4 uWarp;    // x type (0 noise, 1 curl, 2 ripple, 3 off), y scale, z detail (octaves), w swirl (rad)
uniform vec4 uWarp2;   // x swirl radius
uniform vec4 uSono;    // x bands (0 = continuous), y layout (0 low-high, 1 high-low, 2 bass centre, 3 treble centre), z time flow (0 forward, 1 reverse, 2 centre out, 3 edges in), w loudness gamma
uniform vec4 uSono2;   // x onset punch, y overall loudness 0-1
uniform vec4 uMotion;  // x liquid time, y proximity 0-1, z/w viewer centre (uv)
uniform vec4 uPull;    // x pull, y lens, z follow, w proximity zoom
uniform vec4 uImg;     // x visibility, y relief, z spikes, w source (0 full, 1 viewer only, 2 silhouette, 3 edges)
uniform vec4 uImg2;    // x contrast, y invert, z through the kaleidoscope, w gain
uniform vec4 uAmp;     // x amplitude curve, y peak threshold, z peak mix, w aspect (w/h)
uniform vec4 uBass;
uniform vec4 uLowmid;
uniform vec4 uHighmid;
uniform vec4 uTreble;
uniform vec4 uQuiet;
uniform vec4 uPeak;

layout(location = 0) out vec4 fragColor;

const float PI = 3.14159265;
const vec3 LUMA = vec3(0.299, 0.587, 0.114);
// Warp octaves: frequency, time rate and decorrelating offset (octaves 0-1 match v1).
const float WFR[4] = float[](1.3, 3.1, 7.4, 17.6);
const float WTS[4] = float[](0.23, 0.41, 0.73, 1.3);
const float WOF[4] = float[](7.1, 2.3, 4.7, 9.3);

vec2 rot(vec2 v, float a) {
    float c = cos(a), s = sin(a);
    return vec2(c * v.x - s * v.y, s * v.x + c * v.y);
}

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

// Polynomial smooth maximum: neighbouring spikes merge like surface tension.
float smax(float a, float b, float k) {
    float h = clamp(0.5 + 0.5 * (a - b) / k, 0.0, 1.0);
    return mix(b, a, h) + k * h * (1.0 - h);
}

// Nearest cell of a hexagonal lattice with neighbour spacing s: xy = offset from its centre,
// zw = integer cell key. Neighbours sit at 0, 60, 120... degrees; vertices at 30, 90...
vec4 hexCell(vec2 p, float s) {
    vec2 rr = vec2(1.0, 1.7320508) * s;
    vec2 a = mod(p, rr) - 0.5 * rr;
    vec2 b = mod(p - 0.5 * rr, rr) - 0.5 * rr;
    vec2 d = dot(a, a) < dot(b, b) ? a : b;
    return vec4(d, floor((p - d) / (s * vec2(0.5, 0.8660254)) + 0.5));
}

// ---- Sonogram addressing ------------------------------------------------------------

// Display coordinate -> frequency 0 (bass) .. 1 (treble), per layout and band count.
float freqLayout(float u) {
    u = 1.0 - abs(1.0 - mod(u, 2.0));
    if (uSono.y > 2.5) {
        u = 1.0 - abs(2.0 * u - 1.0);   // treble in the middle
    } else if (uSono.y > 1.5) {
        u = abs(2.0 * u - 1.0);         // bass in the middle
    } else if (uSono.y > 0.5) {
        u = 1.0 - u;
    }
    if (uSono.x >= 2.0) {
        u = (floor(min(u, 0.9999) * uSono.x) + 0.5) / uSono.x;
    }
    return u;
}

// Display coordinate -> sonogram time (1 = newest), per time flow.
float timeFlow(float v) {
    v = 1.0 - abs(1.0 - mod(v, 2.0));
    if (uSono.z > 2.5) return abs(2.0 * v - 1.0);
    if (uSono.z > 1.5) return 1.0 - abs(2.0 * v - 1.0);
    if (uSono.z > 0.5) return 1.0 - v;
    return v;
}

vec2 sonoUV(vec2 k) { return vec2(freqLayout(k.x), timeFlow(k.y)); }

float loudness(vec2 suv) {
    vec4 s = texture(sTD2DInputs[0], suv);
    return clamp(pow(s.r, uSono.w) + s.g * uSono2.x, 0.0, 1.5);
}

// ---- Kaleidoscope ----------------------------------------------------------------------

// Point in fluid space -> display uv on the sonogram (x across frequency, y along time).
vec2 kaleido(vec2 q, vec2 centre) {
    q -= centre;
    float mode = uKal.x;
    if (mode < 0.5) {
        return vec2(q.x / uAmp.w, q.y) + 0.5;  // off: the plain sonogram fills the screen
    }
    float zoom = max(uView.x, 0.05);
    float r = length(q);
    // Radial pinch, counter-rotating rings, then spin, sway and twist.
    if (abs(uKal2.x - 1.0) > 1e-3) {
        float rp = pow(r, uKal2.x);
        q *= rp / max(r, 1e-5);
        r = rp;
    }
    if (uKal2.y >= 1.0) {
        q = rot(q, uKal2.z * (mod(floor(r * uKal2.y), 2.0) * 2.0 - 1.0));
    }
    q = rot(q, uKal.z + uKal2.w + uKal.w * r);

    if (mode < 2.5) {
        // Mirror wedges or radial: fold the angle into one wedge.
        float wedge = PI / max(uKal.y, 1.0);
        float a = mod(atan(q.y, q.x), 2.0 * wedge);
        a = wedge - abs(a - wedge);
        if (mode < 1.5) {
            return r * vec2(cos(a), sin(a)) / zoom + 0.5;
        }
        // Radial: angle = frequency, radius = time. Near the centre the spectrum would squeeze
        // into a tiny arc and alias, so it narrows to a calm eye.
        float spread = smoothstep(0.02, 0.35 * zoom, r);
        return vec2(0.5 + (a / wedge - 0.5) * spread, r / zoom);
    }
    q /= zoom;
    if (mode < 5.5) {
        // Tilings: every tile is a small mirrored mandala (frequency by angle, time by radius).
        // Triangle = D3 mirrors through the hexagon vertices (a three-mirror kaleidoscope);
        // Square = D4 mirrors; Hex Cells = D6 mirrors. Each fold keeps the tiles seamless.
        float tile = max(uKal3.z, 0.02);
        vec2 d;
        vec2 key;
        float n;
        float off = 0.0;
        if (mode > 3.5 && mode < 4.5) {
            key = floor(q / tile + 0.5);
            d = q - key * tile;
            n = 4.0;
        } else {
            vec4 h = hexCell(q, tile);
            d = h.xy;
            key = h.zw;
            n = mode < 3.5 ? 3.0 : 6.0;
            off = mode < 3.5 ? PI / 6.0 : 0.0;
        }
        float wedge = PI / n;
        float a = mod(atan(d.y, d.x) - off, 2.0 * wedge);
        a = wedge - abs(a - wedge);
        return vec2(a / wedge, length(d) / (0.5 * tile) + uKal3.w * hash12(key + 5.0));
    }
    if (mode < 6.5) {
        // Fractal: repeated mirror folds, each rotated, shifted and scaled.
        vec2 z = q;
        int it = int(uFrac.x + 0.5);
        for (int i = 0; i < 10; i++) {
            if (i >= it) break;
            z = rot(abs(z) - uFrac.w, uFrac.z) * uFrac.y;
        }
        return z / pow(max(uFrac.y, 1.0), float(it)) + 0.5;
    }
    // Log spiral: endless zoom, arms = segments, time along the log radius.
    float lr = log(max(length(q), 1e-4));
    float a = atan(q.y, q.x);
    return vec2(a / PI * max(uKal.y, 1.0) + lr * uKal.w * 0.5, -lr * 0.35);
}

// The kaleidoscope's mirror wedges applied to a point, staying in fluid space (for the image).
vec2 foldMirror(vec2 q, vec2 centre) {
    vec2 d = q - centre;
    float r = length(d);
    d = rot(d, uKal.z + uKal2.w + uKal.w * r);
    float wedge = PI / max(uKal.y, 1.0);
    float a = mod(atan(d.y, d.x), 2.0 * wedge);
    a = wedge - abs(a - wedge);
    return centre + r * vec2(cos(a), sin(a));
}

// ---- Colour ----------------------------------------------------------------------------

vec3 freqColor(float u) {
    float x = u * 3.0;
    vec3 c = mix(uBass.rgb, uLowmid.rgb, smoothstep(0.0, 1.0, x));
    c = mix(c, uHighmid.rgb, smoothstep(1.0, 2.0, x));
    return mix(c, uTreble.rgb, smoothstep(2.0, 3.0, x));
}

// Colour by frequency (u) and loudness (A).
vec3 soundColor(float u, float A) {
    float a = pow(clamp(A, 0.0, 1.0), uAmp.x);
    vec3 c = mix(uQuiet.rgb, freqColor(u), smoothstep(0.0, uAmp.y, a));
    return mix(c, uPeak.rgb, smoothstep(uAmp.y, 1.0, a) * uAmp.z);
}

// ---- Viewer field and camera picture ---------------------------------------------------

float fieldAt(vec2 uv) { return texture(sTD2DInputs[1], uv).a; }

// Camera picture at screen uv: rgb = colour, a = value (0-1) after source, contrast, invert.
vec4 imageAt(vec2 uv) {
    vec3 c = texture(sTD2DInputs[3], uv).rgb * uImg2.w;
    float l = dot(c, LUMA);
    if (uImg.w > 2.5) {
        vec2 e = uTD2DInfos[3].res.xy * 1.5;
        float lx = dot(texture(sTD2DInputs[3], uv + vec2(e.x, 0.0)).rgb - texture(sTD2DInputs[3], uv - vec2(e.x, 0.0)).rgb, LUMA);
        float ly = dot(texture(sTD2DInputs[3], uv + vec2(0.0, e.y)).rgb - texture(sTD2DInputs[3], uv - vec2(0.0, e.y)).rgb, LUMA);
        l = clamp(length(vec2(lx, ly)) * 4.0, 0.0, 1.0);
    } else if (uImg.w > 0.5) {
        float fv = fieldAt(uv);
        c *= fv;
        l = uImg.w > 1.5 ? fv : l * fv;
    }
    l = clamp((l - 0.5) * uImg2.x + 0.5, 0.0, 1.0);
    if (uImg2.y > 0.5) {
        l = 1.0 - l;
    }
    return vec4(c, l);
}

// Screen uv of the picture for fluid-space point q (pixelQ/pixelUV = the current pixel):
// straight under the viewer, or folded by the kaleidoscope wedges.
vec2 imageUV(vec2 q, vec2 pixelQ, vec2 pixelUV, vec2 centre, float zoomIn) {
    vec2 asp = vec2(uAmp.w, 1.0);
    if (uImg2.z > 0.5) {
        return (centre + (foldMirror(q, centre) - centre) * zoomIn) / asp + 0.5;
    }
    return pixelUV + (q - pixelQ) * zoomIn / asp;
}

// ---- Liquid warp -----------------------------------------------------------------------

float wnoise(vec2 p, float z) { return TDSimplexNoise(vec3(p, z)); }

vec2 warp(vec2 p, vec2 centre, float t) {
    if (uWarp.x > 2.5) {
        return vec2(0.0);
    }
    if (uWarp.x > 1.5) {
        // Radial ripple: waves pushing the surface out from the centre and back.
        vec2 d = p - centre;
        float r = length(d);
        return d / max(r, 1e-4) * sin(r * 14.0 * uWarp.y - t * 2.0);
    }
    vec2 w = vec2(0.0);
    float amp = 1.0;
    int oct = int(uWarp.z + 0.5);
    for (int i = 0; i < 4; i++) {
        if (i >= oct) break;
        vec2 q = p * WFR[i] * uWarp.y;
        float z1 = t * WTS[i] + 3.0 * float(i);
        if (uWarp.x < 0.5) {
            // Noise flow: two decorrelated noise fields push the surface around.
            w += amp * vec2(wnoise(q, z1), wnoise(q + WOF[i], t * WTS[i] + 5.0 * float(i)));
        } else {
            // Curl streams: the curl of a noise field, so the surface swirls without bunching.
            const float e = 0.05;
            float nx = wnoise(q + vec2(e, 0.0), z1) - wnoise(q - vec2(e, 0.0), z1);
            float ny = wnoise(q + vec2(0.0, e), z1) - wnoise(q - vec2(0.0, e), z1);
            w += amp * vec2(ny, -nx) / (2.0 * e) * 0.5;
        }
        amp *= 0.5;
    }
    return w;
}

// ---- Spike profile ---------------------------------------------------------------------

// Height profile of one spike for offset d from its axis and base radius rad.
float spikeProfile(vec2 d, float rad) {
    float shape = uShape.x;
    vec2 a = abs(d);
    float x = (shape > 0.5 && shape < 1.5) ? max(a.x, 0.5 * a.x + 0.8660254 * a.y) / rad : length(d) / rad;
    if (shape < 1.5) {
        return pow(clamp(1.0 - x, 0.0, 1.0), uSpike.z);                     // cone, hexagonal pyramid
    }
    if (shape < 2.5) {
        return pow(max(1.0 - x * x, 0.0), 0.5 / max(uSpike.z, 0.25));       // dome
    }
    return exp(-pow((x - 0.62) * 5.0, 2.0)) * (1.0 - smoothstep(0.95, 1.05, x));  // ring crater
}

void main() {
    float aspect = uAmp.w;
    vec2 uv = vUV.st;
    vec2 p = (uv - 0.5) * vec2(aspect, 1.0);
    float t = uMotion.x;

    // The viewer is the magnet: field strength here and its bounded slope toward the viewer.
    float f = fieldAt(uv);
    float du = 0.012;
    vec2 grad = vec2(fieldAt(uv + vec2(du, 0.0)) - fieldAt(uv - vec2(du, 0.0)),
                     fieldAt(uv + vec2(0.0, du * aspect)) - fieldAt(uv - vec2(0.0, du * aspect))) / (2.0 * du * aspect);
    vec2 pull = grad / (1.0 + length(grad));

    // Kaleidoscope centre (offset, following the viewer); coming closer magnifies the fluid
    // around the centre, and the lens bulges it toward wherever the viewer is.
    vec2 viewer = (uMotion.zw - 0.5) * vec2(aspect, 1.0);
    vec2 centre = uKal3.xy + viewer * uPull.z * smoothstep(0.0, 0.25, uMotion.y);
    float zoomIn = 1.0 + uPull.w * uMotion.y;
    p = centre + (p - centre) / zoomIn;
    p += pull * uPull.y * 0.035;

    // Liquid warp plus a vortex around the centre.
    vec2 pw = p + warp(p, centre, t) * 0.045 * uSpike.y;
    if (abs(uWarp.w) > 1e-4) {
        vec2 dc = pw - centre;
        pw = centre + rot(dc, uWarp.w * exp(-dot(dc, dc) / max(uWarp2.x * uWarp2.x, 1e-4)));
    }

    // Spike lattice (optionally rotated): nearest centre, then it and its neighbours are
    // blended with a smooth maximum. Centres live in lattice space; cw is the same in fluid space.
    float cell = aspect / max(uView.y, 4.0);
    bool hex = uView.z < 0.5;
    float ga = uShape.w;
    vec2 pl = rot(pw, -ga);
    vec2 cen0 = hex ? pl - hexCell(pl, cell).xy : (floor(pl / cell) + 0.5) * cell;

    float boost = 1.0 + uPull.x * f;
    vec2 lean = rot(pull, -ga) * cell * 0.5 * uPull.x;
    float sway = min(uSpike.y, 1.5) * 0.12 * cell;
    float tension = max(uShape2.w, 0.002);
    bool imgSpikes = uImg.z > 0.001;
    float H = 0.0;
    vec3 colAcc = vec3(0.0);
    float wAcc = 0.0;
    float Aown = 0.0;
    float uOwn = 0.5;
    for (int k = 0; k < 9; k++) {
        vec2 off;
        if (hex) {
            if (k > 6) break;
            float ang = float(k - 1) * PI / 3.0;
            off = k == 0 ? vec2(0.0) : vec2(cos(ang), sin(ang));
        } else {
            off = vec2(float(k % 3 - 1), float(k / 3 - 1));
        }
        vec2 c = cen0 + off * cell;
        vec2 key = hex ? floor(c / (cell * vec2(0.5, 0.8660254)) + 0.5) : floor(c / cell);
        float h = hash12(key + 17.0);
        float ph = h * 6.2831853;
        c += vec2(sin(t * 0.9 + ph), cos(t * 0.73 + ph * 1.7)) * sway;
        c += (vec2(hash12(key + 3.1), hash12(key + 7.7)) - 0.5) * cell * 0.6 * uShape2.x;
        vec2 cw = rot(c, ga);
        vec2 suv = sonoUV(kaleido(cw, centre));
        float idle = uSpike.x * (0.6 + 0.4 * sin(dot(cw, vec2(5.1, 3.7)) + t * 1.1) * cos(dot(cw, vec2(-2.9, 4.3)) - t * 0.8));
        float A = max(loudness(suv), idle);
        if (imgSpikes) {
            A = mix(A, imageAt(imageUV(cw, pw, uv, centre, zoomIn)).a, uImg.z);
        }
        if (k == 0) {
            Aown = A;
            uOwn = suv.x;
        }
        float rad = min(cell * uSpike.w * (0.45 + 0.45 * sqrt(A)) * (0.9 + 0.2 * h), cell);
        vec2 d = pl - c;
        float base = clamp(1.0 - length(d) / rad, 0.0, 1.0);
        vec2 dt = d - lean * base;  // the tip leans toward the viewer
        if (uShape.y < 0.5 || uShape.y > 1.5) {
            H = smax(H, spikeProfile(dt, rad) * A * boost, tension);
        }
        float lin = clamp(1.0 - length(dt) / rad, 0.0, 1.0);
        float wgt = lin * lin * (A + 0.02);
        colAcc += soundColor(suv.x, A) * wgt;
        wAcc += wgt;
    }

    // Honeycomb ridges along the cell edges, as high as the two cells they separate.
    if (uShape.y > 0.5) {
        vec2 d0 = pl - cen0;
        vec2 a = abs(d0);
        float side = 0.5 * a.x + 0.8660254 * a.y;
        float edgeDist = 0.5 * cell - (hex ? max(a.x, side) : max(a.x, a.y));
        vec2 nb = hex ? (a.x > side ? vec2(sign(d0.x), 0.0) : vec2(0.5 * sign(d0.x), 0.8660254 * sign(d0.y)))
                      : (a.x > a.y ? vec2(sign(d0.x), 0.0) : vec2(0.0, sign(d0.y)));
        vec2 nbw = rot(cen0 + nb * cell, ga);
        float Anb = max(loudness(sonoUV(kaleido(nbw, centre))), uSpike.x * 0.6);
        if (imgSpikes) {
            Anb = mix(Anb, imageAt(imageUV(nbw, pw, uv, centre, zoomIn)).a, uImg.z);
        }
        float Ar = 0.5 * (Aown + Anb);
        float ridge = pow(1.0 - smoothstep(0.0, max(uShape.z, 0.01) * cell, edgeDist), max(uSpike.z, 0.5) * 0.5 + 0.5);
        H = smax(H, ridge * Ar * boost, tension);
        float wr = ridge * ridge * (Ar + 0.02);
        colAcc += soundColor(uOwn, Ar) * wr;
        wAcc += wr;
    }

    // Nested sub-lattice of small spikes.
    if (uShape2.y > 0.001) {
        float cell2 = cell / max(uShape2.z, 1.0);
        vec2 c2 = hex ? pl - hexCell(pl, cell2).xy : (floor(pl / cell2) + 0.5) * cell2;
        vec2 suv2 = sonoUV(kaleido(rot(c2, ga), centre));
        float A2 = max(loudness(suv2), uSpike.x * 0.6);
        float rad2 = cell2 * uSpike.w * (0.45 + 0.45 * sqrt(A2));
        H = smax(H, spikeProfile(pl - c2, rad2) * A2 * boost * uShape2.y, tension);
        float lin2 = clamp(1.0 - length(pl - c2) / rad2, 0.0, 1.0);
        float w2 = lin2 * lin2 * (A2 + 0.02) * uShape2.y;
        colAcc += soundColor(suv2.x, A2) * w2;
        wAcc += w2;
    }

    // Liquid pool: the same folded sonogram, smooth between spikes and sharp when it is the
    // whole surface (Grid Amount 0), with ripples spreading from the centre as loud as the room.
    vec2 puv = sonoUV(kaleido(pw, centre));
    float sono = mix(texture(sTD2DInputs[0], puv).r, texture(sTD2DInputs[2], puv).r, 0.5 + 0.5 * uView.w);
    float Ap = max(pow(sono, uSono.w), uSpike.x * 0.5);
    vec3 poolCol = soundColor(puv.x, Ap);
    float ripple = uShape3.z * 0.2 * sin(length(pw - centre) * uShape3.w * 6.2831853 - t * 4.0) * (0.35 + uSono2.y);
    float spikes = smax(H, 0.12 * Ap * boost + ripple, 0.04);
    float height = mix(Ap * boost + ripple, spikes, uView.w);
    vec3 spikeCol = mix(poolCol, colAcc / max(wAcc, 1e-4), smoothstep(0.0, 0.04, wAcc));
    vec3 col = mix(poolCol, spikeCol, uView.w);

    // The camera picture: colours the fluid and protrudes from it.
    if (uImg.x > 0.001 || uImg.y > 0.001) {
        vec4 img = imageAt(imageUV(pw, pw, uv, centre, zoomIn));
        height += uImg.y * img.a * 0.8;
        col = mix(col, img.rgb, uImg.x);
    }

    // Spike height, then viscosity: blend with the previous frame.
    vec4 outv = vec4(col, height * uShape3.x);
    outv = mix(outv, texture(sTD2DInputs[4], uv), uShape3.y);
    fragColor = TDOutputSwizzle(outv);
}
