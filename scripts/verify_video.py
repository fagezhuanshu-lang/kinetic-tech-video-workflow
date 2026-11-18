"""Verify a completed movie, its actual BGM, voice clock, and cover/body frames."""
from pathlib import Path
import argparse
import json
import math
import os
import re
import subprocess
import sys
sys.dont_write_bytecode = True
from finish_video import executable, probe, movie_clock, decode, sha256


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--completed', required=True, type=Path, help='Directory produced by finish_video.py')
    p.add_argument('--out', type=Path, help='New QA directory; default completed/qa')
    p.add_argument('--ffmpeg')
    p.add_argument('--ffprobe')
    a = p.parse_args()
    import numpy as np
    from scipy.signal import correlate, correlation_lags
    root = a.completed.resolve()
    out = a.out.resolve() if a.out else root / 'qa'
    if out.exists():
        raise FileExistsError(f'Use a new QA output directory: {out}')
    ffmpeg = executable('ffmpeg', a.ffmpeg)
    ffprobe = executable('ffprobe', a.ffprobe, ffmpeg)
    video = root / 'completed.mp4'
    selection = json.loads((root / 'music-selection.json').read_text(encoding='utf-8'))
    metadata, frames, fps, duration = movie_clock(video, ffprobe)
    v = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in metadata['streams'] if s['codec_type'] == 'audio')
    failures = []

    def check(condition, description):
        if not condition:
            failures.append(description)

    check(frames == selection['frames'], 'Frame count differs from source movie')
    check(abs(duration - selection['duration_seconds']) < 1 / float(fps), 'Duration differs from source movie')
    check(abs(float(audio['duration']) - duration) < .03, 'Audio/video durations differ')
    check(abs(float(audio.get('start_time', 0))) < .001, 'Audio does not start at zero')
    out.mkdir(parents=True, exist_ok=False)
    print('Checking complete decode, audio, first frame, and unchanged body frames', flush=True)
    decoded = subprocess.run([ffmpeg, '-v', 'error', '-i', str(video), '-f', 'null', os.devnull], capture_output=True, text=True)
    full_decode = decoded.returncode == 0 and not decoded.stderr.strip()
    check(full_decode, 'Full decode failed: ' + decoded.stderr.strip())
    loud = subprocess.run([ffmpeg, '-hide_banner', '-nostats', '-i', str(video), '-vn', '-af', 'loudnorm=I=-16:TP=-1:LRA=11:print_format=json', '-f', 'null', os.devnull], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
    loudness = json.loads(re.findall(r'\{[^{}]+\}', loud.stderr)[-1])
    check(-20 < float(loudness['input_i']) < -14, 'Actual loudness outside review range (-20,-14) LUFS')
    check(float(loudness['input_tp']) <= -1, 'Actual true peak exceeds -1 dBTP')
    rate = 8000
    encoded = decode(ffmpeg, video, duration, rate=rate, channels=1).ravel()
    mixed = decode(ffmpeg, root / 'assets/mix.wav', duration, rate=rate, channels=1).ravel()
    without_music = decode(ffmpeg, root / 'assets/without-music-reference.wav', duration, rate=rate, channels=1).ravel()
    music = decode(ffmpeg, root / 'assets/music-bed.wav', duration, rate=rate, channels=1).ravel()

    def correlation(x, y):
        return float(np.corrcoef(x, y)[0, 1]) if np.std(x) and np.std(y) else 0.0

    mixed_correlation = correlation(encoded, mixed)
    # Residual against a counterfactual without music proves that music survives the final AAC.
    design = np.column_stack([without_music, music])
    fit, _, _, _ = np.linalg.lstsq(design, encoded, rcond=None)
    residual = encoded - fit[0] * without_music
    residual_correlation = correlation(residual, music)
    music_rms = float(np.sqrt(np.mean(music ** 2)))
    check(mixed_correlation > .98, 'Encoded audio differs from final WAV mix')
    check(music_rms > 1e-5 and residual_correlation > .85 and .7 < float(fit[1]) < 1.3, 'BGM not confirmed in actual encoded audio')
    voice = decode(ffmpeg, Path(selection['voice_file']), duration, rate=rate, channels=1).ravel()
    window = min(8, duration / 4)
    starts = [min(4, duration * .05), max(0, duration * .5 - window / 2), max(0, duration - window - min(3, duration * .05))]
    sync = []
    for start in starts:
        begin, end = round(start * rate), round((start + window) * rate)
        x, y = voice[begin:end].copy(), encoded[begin:end].copy()
        x -= x.mean(); y -= y.mean()
        denominator = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
        if denominator < 1e-10:
            sync.append({'start': start, 'status': 'insufficient voice energy'})
            continue
        c = correlate(y, x, mode='full', method='fft')
        lags = correlation_lags(len(y), len(x), mode='full')
        mask = np.abs(lags) <= round(.2 * rate)
        index = int(np.argmax(c[mask]))
        delay, similarity = float(lags[mask][index] / rate), float(c[mask][index] / denominator)
        sync.append({'start': start, 'window': window, 'delay_seconds': delay, 'correlation': similarity})
        check(abs(delay) < .04 and similarity > .6, f'Voice alignment failed at {start:.2f}s')
    check(any('delay_seconds' in row for row in sync), 'No usable voice window for alignment')

    def frame(path, index, png=None, cover=False):
        filters = []
        if cover:
            filters.append('scale=in_range=full:out_range=full:out_color_matrix=bt709,format=yuv444p,colorspace=ispace=bt709:irange=pc:iprimaries=bt709:itrc=srgb:space=bt709:range=tv:primaries=bt709:trc=bt709:format=yuv420p')
        else:
            filters.append(f'select=eq(n\\,{index})')
        filters.append('scale=480:270')
        command = [ffmpeg, '-v', 'error', '-i', str(path), '-vf', ','.join(filters), '-frames:v', '1']
        data = np.frombuffer(subprocess.check_output(command + ['-pix_fmt', 'rgb24', '-f', 'rawvideo', '-']), np.uint8)
        if len(data) != 480 * 270 * 3:
            raise ValueError(f'Could not decode frame {index} from {path}')
        if png:
            subprocess.run([ffmpeg, '-v', 'error', '-n', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '480x270', '-i', '-', '-frames:v', '1', str(png)], input=data.tobytes(), check=True)
        return data.astype(float)

    def psnr(x, y):
        mse = float(np.mean((x - y) ** 2))
        return 99.0 if mse == 0 else 10 * math.log10(255 ** 2 / mse)

    actual_cover = frame(video, 0, out / 'frame-00.png')
    expected_cover = frame(root / Path(selection['cover_file']).name, 0, cover=True)
    cover_psnr = psnr(actual_cover, expected_cover)
    check(cover_psnr > 35, 'First frame does not match the selected cover')
    frame_checks = []
    indices = sorted(set([1, min(frames - 1, round(3 * float(fps))), frames // 2, frames - 1]))
    for i, index in enumerate(indices, 1):
        actual = frame(video, index, out / f'frame-{i:02}.png')
        original = frame(Path(selection['silent_video']), index)
        value = psnr(actual, original)
        frame_checks.append({'frame': index, 'psnr_db': value})
        check(value > 35, f'Body frame {index} differs from its original position')
    subprocess.run([ffmpeg, '-v', 'error', '-n', '-framerate', '1', '-i', str(out / 'frame-%02d.png'), '-vf', 'tile=3x2', '-frames:v', '1', str(out / 'contact.jpg')], check=True)
    report = {
        'passed': not failures, 'failures': failures, 'video': str(video), 'sha256': sha256(video),
        'width': v['width'], 'height': v['height'], 'fps': str(fps), 'frames': frames,
        'duration_video': duration, 'duration_audio': float(audio['duration']), 'full_decode_pass': full_decode,
        'loudness_actual': {'integrated_lufs': float(loudness['input_i']), 'true_peak_dbtp': float(loudness['input_tp']), 'range_lu': float(loudness['input_lra'])},
        'bgm_actual': {'mix_vs_encoded_correlation': mixed_correlation, 'residual_vs_music_correlation': residual_correlation, 'fitted_music_gain': float(fit[1]), 'music_rms': music_rms},
        'voice_alignment': sync, 'cover_psnr_db': cover_psnr, 'body_frame_checks': frame_checks,
        'visual_review': 'Automated frame comparisons; inspect contact.jpg and the full-resolution cover separately.',
        'human_listening': 'Not performed by this script; audition the final video to assess music suitability and intelligibility.',
    }
    (out / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError, FileExistsError, subprocess.CalledProcessError, KeyError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        raise SystemExit(1)
