shader_type spatial;
render_mode cull_disabled;
uniform bool section_enabled = true;
uniform vec3 section_normal = vec3(1.0, 0.0, 0.0);
uniform float section_offset = 0.0;
varying vec3 local_position;

void vertex() {
    local_position = VERTEX;
}

void fragment() {
    if (section_enabled && dot(local_position, section_normal) > section_offset) {
        discard;
    }
    ALBEDO = COLOR.rgb;
    ROUGHNESS = 1.0;
}
