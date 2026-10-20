// Viewer presence field from the webcam (160 x 90, mirrored).
// State (fed back): rgb = learned empty-room background, a = presence field 0-1.
// Input 0: current camera frame. Input 1: previous state. Input 2: previous camera frame.
// A seed state with negative rgb (start, or Relearn Background) adopts the current frame as the room.

uniform vec4 uPres;   // x foreground threshold, y presence weight, z motion weight, w motion threshold
uniform vec4 uRates;  // x field attack, y field release, z room learn rate where empty, w where occupied

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec3 cur = texture(sTD2DInputs[0], uv).rgb;
    vec4 state = texture(sTD2DInputs[1], uv);
    if (state.r < -0.5) {
        fragColor = TDOutputSwizzle(vec4(cur, 0.0));
        return;
    }
    vec3 prevCam = texture(sTD2DInputs[2], uv).rgb;
    float fg = smoothstep(uPres.x, uPres.x * 2.0, length(cur - state.rgb));
    float mo = smoothstep(uPres.w, uPres.w * 3.0, length(cur - prevCam));
    float raw = clamp(max(fg * uPres.y, mo * uPres.z), 0.0, 1.0);
    float field = mix(state.a, raw, raw > state.a ? uRates.x : uRates.y);
    vec3 room = mix(state.rgb, cur, mix(uRates.z, uRates.w, fg));
    fragColor = TDOutputSwizzle(vec4(room, field));
}
