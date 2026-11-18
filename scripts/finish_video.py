"""Mix an explicit BGM choice and add a cover to a rendered Kinetic Tech movie."""
from pathlib import Path
from fractions import Fraction
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

SR = 48000


def executable(name, supplied=None, sibling=None):
    candidate = supplied or (str(Path(sibling).with_name(name + Path(sibling).suffix)) if sibling else name)
    found = shutil.which(candidate)
    if not found:
        raise ValueError(f'{name} executable not found: {candidate}')
    return str(Path(found).resolve())


def probe(path, ffprobe):
    return json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def movie_clock(path, ffprobe):
    metadata = probe(path, ffprobe)
    video = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    rate = Fraction(video['r_frame_rate'])
    average = Fraction(video.get('avg_frame_rate', video['r_frame_rate']))
    if (video['width'], video['height']) != (1920, 1080) or rate != 60 or average != rate:
        raise ValueError('This native template workflow requires a 1920x1080 CFR 60 fps render; adapt the layout before using a different specification.')
    if video.get('nb_frames', 'N/A') == 'N/A':
        counted = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries', 'stream=nb_read_frames', '-of', 'json', str(path)]))
        frames = int(counted['streams'][0]['nb_read_frames'])
    else:
        frames = int(video['nb_frames'])
    duration = frames / float(rate)
    if frames < 30 or abs(float(video.get('start_time', 0))) > .001 or abs(float(video['duration']) - duration) > 1 / float(rate):
        raise ValueError('Movie clock must start at zero with consistent frame count and duration (minimum 0.5 seconds).')
    return metadata, frames, rate, duration


def decode(ffmpeg, path, duration, start=0, rate=SR, channels=2):
    import numpy as np
    args = [ffmpeg, '-v', 'error']
    if start:
        args += ['-ss', str(start)]
    args += ['-i', str(path), '-t', str(duration), '-vn', '-ar', str(rate), '-ac', str(channels), '-f', 'f32le', '-']
    data = np.frombuffer(subprocess.check_output(args), np.float32).reshape(-1, channels).astype(np.float64)
    samples = round(duration * rate)
    if len(data) < samples:
        raise ValueError(f'Audio is too short: {path}; need {duration:.6f}s after offset {start}s, got {len(data) / rate:.6f}s. Select another excerpt or prepare an intentional music edit.')
    return data[:samples]


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--instance', required=True, type=Path)
    p.add_argument('--silent-video', required=True, type=Path)
    p.add_argument('--music', required=True, type=Path, help='Explicitly selected local music; never silently omitted or looped.')
    p.add_argument('--music-start', type=float, default=0)
    p.add_argument('--music-name', default=None, help='Known real title or honest local catalog label; omit if unknown.')
    p.add_argument('--music-source', default=None)
    p.add_argument('--music-license', default=None, help='Provenance of an actual permission/license if available; not a license assertion by the script.')
    p.add_argument('--cover', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path, help='A new output directory; existing directories are never overwritten.')
    p.add_argument('--voice', type=Path)
    p.add_argument('--title', default='')
    p.add_argument('--ffmpeg', default=None)
    p.add_argument('--ffprobe', default=None)
    p.add_argument('--voice-lufs', type=float, default=-16)
    p.add_argument('--music-lufs', type=float, default=-22)
    p.add_argument('--duck-db', type=float, default=7)
    p.add_argument('--fade-in', type=float, default=1.2)
    p.add_argument('--fade-out', type=float, default=2)
    return p


def main():
    a = parser().parse_args()
    import numpy as np
    import pyloudnorm as pyln
    import soundfile as sf
    from scipy.ndimage import uniform_filter1d
    if not 0 <= a.music_start or not 0 <= a.duck_db <= 30 or min(a.fade_in, a.fade_out) < 0:
        raise ValueError('Music offset, ducking, and fades must be nonnegative; ducking must be at most 30 dB.')
    if not all(np.isfinite(x) for x in [a.music_start, a.duck_db, a.fade_in, a.fade_out, a.voice_lufs, a.music_lufs]):
        raise ValueError('Audio parameters must be finite.')
    ffmpeg = executable('ffmpeg', a.ffmpeg)
    ffprobe = executable('ffprobe', a.ffprobe, ffmpeg)
    instance, silent, music_source, cover, out = [p.resolve() for p in [a.instance, a.silent_video, a.music, a.cover, a.out]]
    if out.exists():
        raise FileExistsError(f'Preserve existing output; choose a new directory: {out}')
    for path in [silent, music_source, cover, instance / 'settings.json']:
        if not path.is_file():
            raise FileNotFoundError(path)
    settings = json.loads((instance / 'settings.json').read_text(encoding='utf-8-sig'))
    _, frames, fps, duration = movie_clock(silent, ffprobe)
    if abs(float(settings['duration']) - duration) > 1 / float(fps):
        raise ValueError('Instance and silent movie have different timelines.')
    cover_meta = next(s for s in probe(cover, ffprobe)['streams'] if s['codec_type'] == 'video')
    if (cover_meta['width'], cover_meta['height']) != (1920, 1080):
        raise ValueError('Cover must be the native 1920x1080 composition; do not stretch a differently sized image.')
    voice_asset = settings['media']['voice']
    if a.voice is None and voice_asset.get('mode') != 'file':
        raise ValueError('A voice track is required for this talking-head workflow.')
    voice_path = a.voice.resolve() if a.voice else (instance / voice_asset['file']).resolve()
    native_path = instance / 'audio-output/native-sfx.wav'
    punctuation_path = instance / 'audio-output/punctuation.wav'
    for path in [voice_path, native_path, punctuation_path]:
        if not path.is_file():
            raise FileNotFoundError(f'{path}; render/mix the instance first so that its verified native effect stems exist.')
    meter = pyln.Meter(SR)

    def norm(data, target, label):
        loudness = meter.integrated_loudness(data)
        if not np.isfinite(loudness):
            raise ValueError(f'{label} is silent or cannot be normalized.')
        return data * 10 ** ((target - loudness) / 20)

    print('Decoding and mixing voice, selected music, and native sound effects', flush=True)
    voice = norm(decode(ffmpeg, voice_path, duration), a.voice_lufs, 'Voice')
    music = norm(decode(ffmpeg, music_source, duration, a.music_start), a.music_lufs, 'Music')
    native = decode(ffmpeg, native_path, duration)
    punctuation = decode(ffmpeg, punctuation_path, duration)
    samples = len(voice)
    energy = np.sqrt(np.maximum(0, uniform_filter1d(np.mean(voice * voice, axis=1), size=round(.04 * SR))))
    gate = uniform_filter1d((energy > .007).astype(float), size=round(.25 * SR))
    music *= 10 ** (-a.duck_db * np.clip(gate * 2, 0, 1) / 20)[:, None]
    fade_in, fade_out = min(samples, round(a.fade_in * SR)), min(samples, round(a.fade_out * SR))
    if fade_in:
        music[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    if fade_out:
        music[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None] ** 1.3
    without_music = voice + native + punctuation
    # Apply the same accepted movie-end taper to both stems for meaningful residual QA.
    tail = min(samples, round(.6 * SR))
    fade = np.linspace(1, 0, tail)[:, None] ** 1.3
    without_music[-tail:] *= fade
    music[-tail:] *= fade
    full = without_music + music
    gain = 10 ** ((-17 - meter.integrated_loudness(full)) / 20)
    out.mkdir(parents=True, exist_ok=False)
    assets = out / 'assets'
    assets.mkdir()
    sf.write(assets / 'music-bed.wav', music * gain, SR, subtype='PCM_24')
    sf.write(assets / 'prelimit.wav', full * gain, SR, subtype='FLOAT')
    sf.write(assets / 'without-music-prelimit.wav', without_music * gain, SR, subtype='FLOAT')
    limiter = 'aresample=192000,alimiter=limit=0.65:level=false:latency=true:attack=5:release=100,aresample=48000'
    for source, target in [('prelimit.wav', 'mix.wav'), ('without-music-prelimit.wav', 'without-music-reference.wav')]:
        subprocess.run([ffmpeg, '-v', 'error', '-n', '-i', str(assets / source), '-af', limiter, '-c:a', 'pcm_s24le', str(assets / target)], check=True)
    local_cover = out / ('cover' + cover.suffix.lower())
    shutil.copy2(cover, local_cover)
    final = out / 'completed.mp4'
    provenance = {
        'format_version': 1, 'instance': str(instance), 'silent_video': str(silent),
        'voice_file': str(voice_path), 'cover_file': str(local_cover), 'cover_input': str(cover),
        'music_file': str(music_source), 'music_sha256': sha256(music_source),
        'music_name': a.music_name, 'music_source': a.music_source or str(music_source),
        'music_license_supplied': a.music_license,
        'rights_note': 'Source records are not a commercial license assertion. No music title, artist, or permission is inferred from cache filenames.',
        'music_selection_seconds': [a.music_start, a.music_start + duration],
        'voice_target_lufs': a.voice_lufs, 'music_before_duck_lufs': a.music_lufs, 'duck_db': a.duck_db,
        'fade_in_seconds': a.fade_in, 'fade_out_seconds': a.fade_out,
        'music_bed_lufs': float(meter.integrated_loudness(music * gain)),
        'voice_lufs_before_limiter': float(meter.integrated_loudness(voice * gain)),
        'mix_target_lufs_before_limiter': -17, 'limiter_ceiling_amplitude': .65,
        'duration_seconds': duration, 'frames': frames, 'fps': str(fps),
        'native_stems': [str(native_path), str(punctuation_path)],
        'cover_policy': 'Replace frame zero only. Preserve all subsequent frame positions and the voice clock.',
        'cover_color_assumption': 'Input cover is an sRGB PNG/JPEG rendered by render_cover.mjs.',
    }
    (out / 'music-selection.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Encoding final movie with the cover in frame zero', flush=True)
    cover_filter = 'scale=in_range=full:out_range=full:out_color_matrix=bt709,format=yuv444p,colorspace=ispace=bt709:irange=pc:iprimaries=bt709:itrc=srgb:space=bt709:range=tv:primaries=bt709:trc=bt709:format=yuv420p'
    threshold = .5 / float(fps)
    filters = f"[1:v]{cover_filter}[cover];[0:v][cover]overlay=0:0:enable='lt(t,{threshold:.12f})':eof_action=repeat:repeatlast=1:shortest=0,format=yuv420p[v]"
    command = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-n', '-i', str(silent), '-i', str(local_cover), '-i', str(assets / 'mix.wav'),
        '-filter_complex', filters, '-map', '[v]', '-map', '2:a:0', '-frames:v', str(frames), '-r', str(fps),
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '17', '-pix_fmt', 'yuv420p',
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv',
        '-c:a', 'aac', '-b:a', '256k', '-ar', str(SR), '-t', str(duration), '-movflags', '+faststart']
    if a.title:
        command += ['-metadata', 'title=' + a.title]
    command += ['-progress', str(assets / 'encode-progress.txt'), str(final)]
    (assets / 'encode-command.json').write_text(json.dumps(command, ensure_ascii=False, indent=2), encoding='utf-8')
    with (assets / 'encode-log.txt').open('w', encoding='utf-8') as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    result = {'video': str(final), 'bytes': final.stat().st_size, 'sha256': sha256(final), 'frames': frames, 'duration': duration, 'music_bed_lufs': provenance['music_bed_lufs']}
    (out / 'build-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError, FileExistsError, subprocess.CalledProcessError, KeyError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        raise SystemExit(1)
