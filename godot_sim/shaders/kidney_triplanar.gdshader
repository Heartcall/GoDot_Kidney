shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform sampler2D albedo_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform float tex_scale : hint_range(0.1, 20.0) = 2.5;
uniform float blend_sharpness : hint_range(1.0, 32.0) = 6.0;
uniform float roughness_value : hint_range(0.0, 1.0) = 0.85;
uniform float specular_value : hint_range(0.0, 1.0) = 0.15;
uniform vec4 wet_tint : source_color = vec4(1.0, 0.85, 0.85, 1.0);
uniform float clearcoat_value : hint_range(0.0, 1.0) = 0.3;
// Higher = softer/broader wet-coat highlight. Previously hardcoded at 0.2,
// which produced a small, hard, near-pure-white specular point on every
// frame -- CycleGAN learned to treat that isolated sharp dot as a special
// trigger and hallucinate a large, unstable, wrongly-colored blob over it
// in the style-transferred output. Raising this spreads the same reflected
// energy over a wider, softer area instead.
uniform float clearcoat_roughness_value : hint_range(0.0, 1.0) = 0.2;
// When true, skip the texture entirely and use flat_color as ALBEDO
// directly -- for a plain untextured tissue look (e.g. for a cleaner
// synthetic-domain baseline going into CycleGAN).
uniform bool use_flat_color = false;
uniform vec4 flat_color : source_color = vec4(0.9, 0.4, 0.55, 1.0);

varying vec3 world_pos;
varying vec3 world_normal;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec3 n = normalize(world_normal);
	if (!FRONT_FACING) {
		n = -n;
	}

	vec3 blend = pow(abs(n), vec3(blend_sharpness));
	blend /= (blend.x + blend.y + blend.z + 0.00001);

	vec2 uv_x = world_pos.yz * tex_scale;
	vec2 uv_y = world_pos.xz * tex_scale;
	vec2 uv_z = world_pos.xy * tex_scale;

	vec4 col_x = texture(albedo_texture, uv_x);
	vec4 col_y = texture(albedo_texture, uv_y);
	vec4 col_z = texture(albedo_texture, uv_z);

	vec4 albedo = col_x * blend.x + col_y * blend.y + col_z * blend.z;
	albedo.rgb *= wet_tint.rgb;

	if (use_flat_color) {
		albedo = flat_color;
	}

	ALBEDO = albedo.rgb;
	ROUGHNESS = roughness_value;
	SPECULAR = specular_value;
	// subtle wet-tissue highlight
	CLEARCOAT = clearcoat_value;
	CLEARCOAT_ROUGHNESS = clearcoat_roughness_value;
}
