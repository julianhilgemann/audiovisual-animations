// mat_cloud vertex: one camera-facing soft dot per instance of geo_cloud.
// Instance i reads texel (i % W, i / W) of sPos (null_field: xyz, radius) and
// sCol (null_color: rgb). The rectangle SOP (-0.5..0.5) becomes the billboard.
// Depth of field: a dot away from the focus distance grows by its circle of
// confusion and spreads the same light over the larger disc (bokeh).
uniform sampler2D sPos;
uniform sampler2D sCol;
uniform vec4 uFade;   // x fade start distance, y fade end distance, z brightness at the far end,
                      // w reference distance: dots closer than this dim by (dist/w)^2
uniform vec4 uDof;    // x focus distance, y blur radius per unit of defocus, z max blur radius

out Vertex {
	vec4 color;
	vec2 corner;
	flat int cameraIndex;
} oVert;

void main() {
	int id = TDInstanceID();
	ivec2 res = textureSize(sPos, 0);
	ivec2 c = ivec2(id % res.x, id / res.x);
	vec4 p = texelFetch(sPos, c, 0);
	vec4 col = texelFetch(sCol, c, 0);
	int cam = TDCameraIndex();
	vec4 world = TDDeform(p.xyz);
	vec3 right = uTDMats[cam].camInverse[0].xyz;
	vec3 up = uTDMats[cam].camInverse[1].xyz;
	vec2 corner = TDPos().xy * 2.0;
	float dist = length(world.xyz - uTDMats[cam].camInverse[3].xyz);
	float radius = p.w + min(uDof.z, abs(dist - uDof.x) * uDof.y);
	world.xyz += (right * corner.x + up * corner.y) * radius;
	float fade = mix(1.0, uFade.z, smoothstep(uFade.x, uFade.y, dist));
	fade *= clamp(pow(dist / uFade.w, 2.0), 0.06, 1.0);
	fade *= pow(p.w / radius, 1.8);
	gl_Position = TDWorldToProj(world);
	oVert.color = vec4(col.rgb * fade, 1.0);
	oVert.corner = corner;
	oVert.cameraIndex = cam;
}
