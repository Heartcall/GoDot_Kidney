shader_type canvas_item;

uniform float distortion : hint_range(-1.0, 1.0) = 0.35;
uniform float chroma_aberration : hint_range(0.0, 0.02) = 0.004;
uniform float vignette_radius : hint_range(0.1, 1.5) = 0.7;
uniform float vignette_softness : hint_range(0.05, 1.5) = 0.6;
uniform vec4 vignette_color : source_color = vec4(0.0, 0.0, 0.0, 1.0);

void fragment() {
	vec2 uv = UV * 2.0 - 1.0;
	float r2 = dot(uv, uv);

	// The strongest per-channel distortion (R, at the frame corners where r2=2.0)
	// pushes the sample position past the texture edge, which would otherwise get
	// forced to black below. Pre-zoom the base uv so that worst case lands exactly
	// on the texture edge instead of past it, guaranteeing full-frame coverage.
	float corner_factor = 1.0 + (distortion + chroma_aberration) * 2.0;
	vec2 zoomed_uv = uv / max(corner_factor, 0.0001);

	vec2 uv_r = zoomed_uv * (1.0 + (distortion + chroma_aberration) * r2);
	vec2 uv_g = zoomed_uv * (1.0 + distortion * r2);
	vec2 uv_b = zoomed_uv * (1.0 + (distortion - chroma_aberration) * r2);

	uv_r = uv_r * 0.5 + 0.5;
	uv_g = uv_g * 0.5 + 0.5;
	uv_b = uv_b * 0.5 + 0.5;

	bool outside = uv_g.x < 0.0 || uv_g.x > 1.0 || uv_g.y < 0.0 || uv_g.y > 1.0;

	float r_ch = texture(TEXTURE, clamp(uv_r, 0.0, 1.0)).r;
	float g_ch = texture(TEXTURE, clamp(uv_g, 0.0, 1.0)).g;
	float b_ch = texture(TEXTURE, clamp(uv_b, 0.0, 1.0)).b;

	vec3 col = vec3(r_ch, g_ch, b_ch);

	float vig = smoothstep(vignette_radius, vignette_radius - vignette_softness, length(uv));
	col = mix(vignette_color.rgb, col, vig);
	col = mix(col, vec3(0.0), float(outside));

	COLOR = vec4(col, 1.0);
}
