// Reduce the presence field to one pixel for the CHOPs:
// r,g = field-weighted centre of the viewer (0-1 uv), b = mean field (how much of the
// frame the viewer fills, the proximity cue), a = peak field.

layout(location = 0) out vec4 fragColor;

void main() {
    const int NX = 32;
    const int NY = 18;
    vec3 acc = vec3(0.0);
    float peak = 0.0;
    for (int j = 0; j < NY; j++) {
        for (int i = 0; i < NX; i++) {
            vec2 uv = (vec2(i, j) + 0.5) / vec2(NX, NY);
            float f = texture(sTD2DInputs[0], uv).a;
            acc += vec3(uv * f, f);
            peak = max(peak, f);
        }
    }
    vec2 centre = acc.z > 0.001 ? acc.xy / acc.z : vec2(0.5);
    fragColor = TDOutputSwizzle(vec4(centre, acc.z / float(NX * NY), peak));
}
