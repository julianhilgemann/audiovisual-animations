// Ferrofluid shading. Normals come from the height field; the body is a near-black mirror
// that shows the sound colour on its flanks (a coloured horizon reflection), crisp softbox
// highlights on the tips, and an emissive glow on tall loud spikes.
// Input 0: fluid (rgb colour, a height). Input 1: presence field (A). Input 2: sonogram (R).

uniform vec4 uLook;   // x relief, y gloss, z reflection, w body colour
uniform vec4 uLight;  // x tip glow, y key light, z sound colour rim, w grid cell size in pixels
uniform vec4 uView;   // x debug view (0 off, 1 field, 2 sonogram, 3 height), y/z viewer centre uv, w light follows viewer
uniform vec4 uKey;    // key light colour
uniform vec4 uExtra;  // x sonogram glow

layout(location = 0) out vec4 fragColor;

float heightAt(ivec2 p) {
    ivec2 last = ivec2(uTDOutputInfo.res.zw) - 1;
    return texelFetch(sTD2DInputs[0], clamp(p, ivec2(0), last), 0).a;
}

void main() {
    ivec2 px = ivec2(gl_FragCoord.xy);
    vec4 s = texelFetch(sTD2DInputs[0], px, 0);
    vec3 tint = s.rgb;
    float h = s.a;

    // Slope per grid cell, so the relief reads the same at any grid density.
    vec2 g = vec2(heightAt(px + ivec2(1, 0)) - heightAt(px - ivec2(1, 0)),
                  heightAt(px + ivec2(0, 1)) - heightAt(px - ivec2(0, 1))) * 0.5 * uLight.w * uLook.x;
    vec3 n = normalize(vec3(-g, 1.0));

    // Key light from the upper left, swinging toward the viewer.
    vec2 toViewer = (uView.yz - 0.5) * 1.6;
    vec3 L = normalize(vec3(mix(vec2(-0.55, 0.6), toViewer, uView.w), 0.75));
    vec3 V = vec3(0.0, 0.0, 1.0);
    vec3 R = reflect(-V, n);
    float ndl = max(dot(n, L), 0.0);
    float fres = 0.04 + 0.96 * pow(1.0 - max(n.z, 0.0), 5.0);

    // Environment: a dark room overhead, a white softbox on the key side and a low ring
    // light in the sound colour on the opposite side, so every spike reads as a glossy cone:
    // white highlight on one flank, coloured rim on the other, black in between.
    float grazing = smoothstep(0.1, 0.8, 1.0 - R.z);
    vec2 rimDir = -normalize(L.xy);
    float rimSide = pow(max(dot(normalize(R.xy + 1e-5), rimDir), 0.0), 2.0);
    vec3 env = tint * grazing * (0.12 + rimSide) * uLight.z;
    env += uKey.rgb * smoothstep(0.955, 0.985, dot(R, L)) * uLight.y * 2.5;
    float spec = pow(max(dot(n, normalize(L + V)), 0.0), uLook.y) * uLight.y;

    float ao = mix(0.25, 1.0, smoothstep(0.0, 0.3, h));
    vec3 body = tint * uLook.w * (0.2 + 0.8 * ndl) * ao;
    vec3 col = body
             + env * mix(0.35, 1.0, fres) * uLook.z
             + uKey.rgb * spec
             + tint * uLight.x * min(h, 1.5) * min(h, 1.5)
             + tint * uExtra.x;  // sonogram glow, independent of height

    if (uView.x > 0.5) {
        vec2 uv = vUV.st;
        vec3 dbg = uView.x < 1.5 ? vec3(1.0, 0.45, 0.1) * texture(sTD2DInputs[1], uv).a
                 : uView.x < 2.5 ? vec3(texture(sTD2DInputs[2], uv).r)
                 : vec3(h);
        col = mix(col, dbg, 0.7);
    }
    fragColor = TDOutputSwizzle(vec4(col, 1.0));
}
