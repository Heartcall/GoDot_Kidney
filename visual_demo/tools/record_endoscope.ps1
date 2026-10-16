param(
    [double]$Duration = 8,
    [int]$Fps = 30,
    [double]$Start = 0.5778149846,
    [double]$End = 0.6933779815,
    [string]$Name = 'endoscope_v3_final',
    [string]$Godot = 'E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe',
    [string]$Ffmpeg = ''
)
$ErrorActionPreference = 'Stop'
if ($Name -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Name must be a plain filename stem.' }
if ($Duration -le 0 -or $Fps -lt 1 -or $Start -lt 0 -or $End -gt 1 -or $Start -gt $End) { throw 'Invalid duration, fps or progress range.' }
if ([Math]::Abs($Duration*$Fps - [Math]::Round($Duration*$Fps/2)*2) -gt 0.00001) { throw 'Duration * Fps must be an even integer so start, exact peak and end are captured.' }
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$project = Join-Path $repo 'godot_sim'
$override = Join-Path $project 'override.cfg'
$recordings = Join-Path $project 'recordings'
$logs = Join-Path $repo 'visual_demo/endoscope_v1/reports'
if (Test-Path -LiteralPath $override) { throw 'Existing override.cfg found; preserve it. Resolve recording settings explicitly.' }
New-Item -ItemType Directory -Force $recordings,$logs | Out-Null
$settings = @'
; Temporary Movie Maker settings. Original project.godot is untouched.
[display]
window/size/viewport_width.movie=1920
window/size/viewport_height.movie=1080
window/size/window_width_override.movie=960
window/size/window_height_override.movie=540
window/stretch/mode.movie="viewport"
window/stretch/aspect.movie="keep"
[editor]
movie_writer/video_quality=0.95
'@
try {
    [IO.File]::WriteAllText($override, $settings, [Text.UTF8Encoding]::new($false))
    & $Godot --path $project res://visual_demo_endoscope_video.tscn --write-movie "recordings/$Name.avi" --fixed-fps $Fps --disable-vsync --log-file "$logs/$Name.log" -- "--duration=$Duration" "--start=$Start" "--end=$End" "--report=res://recordings/$Name" --audit
    if ($LASTEXITCODE -ne 0) { throw "Godot failed: $LASTEXITCODE" }
} finally {
    # Only remove the exact temporary config this invocation created.
    if ((Test-Path -LiteralPath $override) -and ([IO.File]::ReadAllText($override) -eq $settings)) {
        Remove-Item -LiteralPath $override
    }
}
$runtime = Get-Content -LiteralPath (Join-Path $recordings "$($Name)_runtime.json") -Raw | ConvertFrom-Json
if (-not $runtime.finished_normally) { throw 'The scene did not finish normally.' }
if (-not $Ffmpeg) { $Ffmpeg = Join-Path $repo 'visual_demo/endoscope_v1/vendor/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe' }
if (-not (Test-Path -LiteralPath $Ffmpeg)) { throw 'AVI is complete. Pass -Ffmpeg with your FFmpeg executable to convert to MP4.' }
# Keep the exact final state; remove Movie Maker's extra post-quit duplicate.
& $Ffmpeg -y -hide_banner -i (Join-Path $recordings "$Name.avi") -an -frames:v $runtime.frames -vf 'scale=in_color_matrix=bt601:out_color_matrix=bt709:in_range=pc:out_range=tv' -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -color_range tv -colorspace bt709 -color_trc bt709 -color_primaries bt709 -video_track_timescale 15360 -movflags +faststart (Join-Path $recordings "$Name.mp4") 2> (Join-Path $logs "$($Name)_ffmpeg.log")
if ($LASTEXITCODE -ne 0) { throw 'FFmpeg conversion failed; original AVI is preserved.' }
Write-Output "Finished: $recordings/$Name.mp4"
