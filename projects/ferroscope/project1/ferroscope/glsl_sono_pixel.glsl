// Sonogram history: the newest spectrum is written on the top row every frame and
// older rows scroll down, so sound flows from top to bottom.
// R = loudness 0-1 (dB-normalised, attack/release smoothed), G = onset (rising edge) 0-1,
// B (top row only) = Auto Gain's tracked peak in dB.
// Input 0: this shader's previous output (feedback). Input 1: the spectrum, one row.

uniform vec4 uSono;    // x rows to scroll this frame, y manual gain dB, z dynamic range dB, w treble tilt dB
uniform vec4 uSmooth;  // x attack coefficient, y release coefficient, z spectrum start, w spectrum end
uniform vec4 uAgc;     // x auto gain on, y peak fall in dB per frame, z silence level dB
uniform vec4 uSmooth2; // x smoothing across frequency, in bins

float bandDb(float u) {
    float mag = texture(sTD2DInputs[1], vec2(mix(uSmooth.z, uSmooth.w, u), 0.5)).r;
    return 8.6858896 * log(max(mag, 1e-7)) + uSono.w * u;  // 20*log10(x) = 8.686*ln(x), plus tilt
}

layout(location = 0) out vec4 fragColor;

void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    ivec2 size = ivec2(uTDOutputInfo.res.zw);
    int top = size.y - 1;
    if (p.y < top) {
        int shift = int(uSono.x + 0.5);
        fragColor = TDOutputSwizzle(texelFetch(sTD2DInputs[0], ivec2(p.x, min(p.y + shift, top)), 0));
        return;
    }
    vec4 prev = texelFetch(sTD2DInputs[0], ivec2(p.x, top), 0);

    // Auto Gain: every top-row pixel scans the whole spectrum for the loudest band (same result
    // in each), holds it with a slow fall, and never drops below the silence level.
    float rowMax = -200.0;
    for (int i = 0; i < 128; i++) {
        rowMax = max(rowMax, bandDb((float(i) + 0.5) / 128.0));
    }
    float peakPrev = prev.b < -0.5 ? prev.b : rowMax;  // 0 = unset (seed or cleared)
    float peak = max(max(rowMax, peakPrev - uAgc.y), uAgc.z);
    float gain = uAgc.x > 0.5 ? -peak : uSono.y;

    float u = (float(p.x) + 0.5) / float(size.x);
    float db = bandDb(u);
    if (uSmooth2.x > 0.25) {
        // Gaussian blur across neighbouring frequencies (in dB), smoothing blocky bass bins.
        float acc = 0.0;
        float wsum = 0.0;
        for (int i = -4; i <= 4; i++) {
            float w = exp(-float(i * i) / 8.0);
            acc += bandDb(u + float(i) * uSmooth2.x / (4.0 * float(size.x))) * w;
            wsum += w;
        }
        db = acc / wsum;
    }
    float target = clamp(1.0 + (db + gain) / max(uSono.z, 1.0), 0.0, 1.0);
    float amp = mix(prev.r, target, target > prev.r ? uSmooth.x : uSmooth.y);
    float onset = max(clamp((target - prev.r) * 3.0, 0.0, 1.0), prev.g * 0.85);
    fragColor = TDOutputSwizzle(vec4(amp, onset, peak, 1.0));
}
