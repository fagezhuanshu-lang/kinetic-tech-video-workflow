"""Run the complete native-template, music, cover, and verification workflow."""
from pathlib import Path
import argparse
import copy
import datetime
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'


def read_json(path):
    def reject(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=reject)


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_path(value, base):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    if path.is_symlink() or not path.is_file():
        raise ValueError('Input must be an existing regular file: ' + str(path))
    return path.resolve()


def environment(work, config):
    env = os.environ.copy()
    bins = [str(Path(config[key]).parent) for key in ['python', 'node', 'ffmpeg', 'ffprobe']]
    env['PATH'] = os.pathsep.join(dict.fromkeys([*bins, env.get('PATH', '')]))
    temp = work / 'temp'
    temp.mkdir(parents=True, exist_ok=True)
    for name in ['TEMP', 'TMP', 'TMPDIR']:
        env[name] = str(temp)
    env['PYTHONUTF8'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['CHROME'] = config['chrome']
    env['KINETIC_RUNTIME_HOME'] = str(work)
    return env


def load_runtime(work, bootstrap):
    if bootstrap:
        subprocess.run([sys.executable, str(SCRIPTS / 'runtime.py'), '--work', str(work), 'bootstrap'], check=True)
    state_file = work / 'runtime.json'
    if not state_file.is_file():
        raise ValueError('Runtime is not configured. Run scripts/runtime.py --work "' + str(work) + '" bootstrap, or add --bootstrap to this command.')
    config = read_json(state_file)
    for key in ['python', 'node', 'ffmpeg', 'ffprobe', 'chrome', 'template']:
        if not isinstance(config.get(key), str) or not Path(config[key]).exists():
            raise ValueError('Runtime path is missing: ' + key + '. Run runtime.py doctor and bootstrap in a new runtime directory.')
    return config


def validate_schema(value, schema, config, env):
    # The entry point uses only stdlib; jsonschema is provided by the configured runtime.
    code = ('import json,sys;from jsonschema import Draft202012Validator;'
            'p=json.load(sys.stdin);e=sorted(Draft202012Validator(p["schema"]).iter_errors(p["value"]),key=lambda e:str(list(e.path)));'
            'print("valid" if not e else str(list(e[0].path))+": "+e[0].message);sys.exit(bool(e))')
    result = subprocess.run([config['python'], '-c', code], input=json.dumps({'schema': schema, 'value': value}, ensure_ascii=False, allow_nan=False),
                            capture_output=True, text=True, encoding='utf-8', env=env)
    if result.returncode:
        raise ValueError('Schema validation failed: ' + (result.stdout.strip() or result.stderr.strip()))


def prepare_inputs(job_file, config, env):
    job = read_json(job_file)
    validate_schema(job, read_json(ROOT / 'schemas/job.schema.json'), config, env)
    input_file = file_path(job['user_input'], job_file.parent)
    native = read_json(input_file)
    validate_schema(native, read_json(ROOT / 'assets/template/params.schema.json'), config, env)
    media = native.get('media', {})
    if media.get('voice', {}).get('mode') != 'file':
        raise ValueError('The complete talking-head workflow requires media.voice.mode=file. Supply a real narration track; automatic speech generation is not bundled.')
    if native.get('soundEffects') != 'native':
        raise ValueError('This complete workflow expects soundEffects=native. Use the lower-level scripts for a deliberately different audio policy.')
    if not native.get('captions'):
        raise ValueError('Provide measured or supplied sentence captions in user.json. Automatic transcription is not bundled; captions must not be invented.')
    normalized = copy.deepcopy(native)
    inputs = [job_file, input_file]

    def normalize_media(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'file' and isinstance(child, str):
                    resolved = file_path(child, input_file.parent)
                    value[key] = str(resolved)
                    inputs.append(resolved)
                else:
                    normalize_media(child)
        elif isinstance(value, list):
            for child in value:
                normalize_media(child)

    # Native render supplies effects and a preview; final BGM is mixed once by finish_video.
    normalized['media']['music'] = {'mode': 'none'}
    normalize_media(normalized['media'])
    selected_music = file_path(job['music']['file'], job_file.parent)
    job['music']['file'] = str(selected_music)
    inputs.append(selected_music)
    cover = job['cover']
    if 'frame' in cover:
        cover['frame'] = str(file_path(cover['frame'], job_file.parent))
        inputs.append(Path(cover['frame']))
    if 'instance_frame' in cover:
        relative = Path(cover['instance_frame'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('cover.instance_frame must stay inside the prepared instance.')
    if 'frame_time' in cover and normalized['media'].get('presenter', {}).get('mode') != 'video':
        raise ValueError('cover.frame_time requires a presenter video; use cover.frame for an external still image.')
    records = [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in dict.fromkeys(inputs)]
    return job, normalized, records


def timecode(value):
    milliseconds = round(float(value) * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}'


def run_job(args, work, config, env, job, normalized, records):
    out = args.out.expanduser().resolve()
    if out.exists():
        raise FileExistsError('Preserve existing output. Choose a new --out directory; inspect workflow-state.json and logs in the previous run before retrying.')
    out.mkdir(parents=True, exist_ok=False)
    logs = out / 'logs'
    logs.mkdir()
    write_json(out / 'job.resolved.json', job)
    write_json(out / 'user.resolved.json', normalized)
    write_json(out / 'input-hashes.json', records)
    state = {'format_version': 1, 'status': 'running', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'job': str(args.job.resolve()), 'runtime': str(work), 'inputs': records, 'stages': [], 'delivery': None}
    state_file = out / 'workflow-state.json'
    write_json(state_file, state)
    python = config['python']
    runtime = [python, str(SCRIPTS / 'runtime.py'), '--work', str(work), 'template']

    def stage(name, command):
        row = {'name': name, 'status': 'running', 'log': f'logs/{name}.txt'}
        state['stages'].append(row)
        write_json(state_file, state)
        print('Starting ' + name, flush=True)
        with (logs / (name + '.txt')).open('w', encoding='utf-8') as log:
            result = subprocess.run([str(x) for x in command], cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT)
        row['exit_code'] = result.returncode
        row['status'] = 'passed' if result.returncode == 0 else 'failed'
        write_json(state_file, state)
        if result.returncode:
            raise RuntimeError(f'{name} failed (exit {result.returncode}). Read {logs / (name + ".txt")}; no final delivery is marked complete.')
        print('Passed ' + name, flush=True)

    try:
        user = out / 'user.resolved.json'
        instance = out / 'instance'
        silent = out / 'silent.mp4'
        cover_out = out / 'cover'
        complete = out / 'delivery'
        stage('plan', [*runtime, 'plan', '--input', user, '--out', out / 'plan.json'])
        plan = read_json(out / 'plan.json')
        duration = float(plan['duration_s'])
        if 'frame_time' in job['cover'] and job['cover']['frame_time'] >= duration:
            raise ValueError('cover.frame_time must be less than the actual planned duration.')
        preview_time = job.get('preview_time', min(3, duration / 2))
        if preview_time >= duration:
            raise ValueError('preview_time must be less than actual planned duration.')
        stage('prepare', [*runtime, 'prepare', '--input', user, '--out', instance])
        stage('preview', [*runtime, 'preview', '--instance', instance, '--out', out / 'preview.png', '--time', preview_time])
        stage('render', [*runtime, 'render', '--instance', instance, '--out', silent])
        settings = read_json(instance / 'settings.json')
        cover = job['cover']
        if 'frame' in cover:
            frame = Path(cover['frame'])
        elif 'instance_frame' in cover:
            frame = (instance / cover['instance_frame']).resolve()
        else:
            presenter = settings['presenter']
            index = round(cover['frame_time'] * presenter['fps'])
            if not 0 <= index < presenter['frames']:
                raise ValueError('Selected cover frame is outside the prepared presenter sequence.')
            frame = instance / presenter['directory'] / f'{index:05d}.jpg'
        if not frame.is_file():
            raise FileNotFoundError('Cover frame is missing: ' + str(frame))
        command = [config['node'], str(SCRIPTS / 'render_cover.mjs'), '--work', str(work), '--instance', str(instance),
                   '--out', str(cover_out), '--presenter-frame', str(frame), '--title', cover['title']]
        for key in ['label', 'subtitle', 'footer']:
            if key in cover:
                command += ['--' + key, cover[key]]
        stage('cover', command)
        command = [python, str(SCRIPTS / 'finish_video.py'), '--instance', str(instance), '--silent-video', str(silent),
                   '--music', job['music']['file'], '--music-start', str(job['music'].get('start', 0)),
                   '--cover', str(cover_out / 'cover.png'), '--out', str(complete), '--title', cover['title'],
                   '--ffmpeg', config['ffmpeg'], '--ffprobe', config['ffprobe']]
        for key in ['name', 'source', 'license']:
            if key in job['music']:
                command += ['--music-' + key, job['music'][key]]
        for key, value in job.get('mix', {}).items():
            command += ['--' + key.replace('_', '-'), str(value)]
        stage('finish', command)
        stage('verify', [python, str(SCRIPTS / 'verify_video.py'), '--completed', complete,
                         '--ffmpeg', config['ffmpeg'], '--ffprobe', config['ffprobe']])
        for name in ['cover.png', 'cover.jpg', 'cover-provenance.json']:
            source, target = cover_out / name, complete / name
            if target.exists():
                if sha(source) != sha(target):
                    raise RuntimeError('Conflicting final cover: ' + name)
            else:
                shutil.copy2(source, target)
        captions = normalized['captions']
        srt = '\n\n'.join(f'{i}\n{timecode(cue["start"])} --> {timecode(cue["end"])}\n{cue["text"]}' for i, cue in enumerate(captions, 1)) + '\n'
        (complete / 'captions.srt').write_text(srt, encoding='utf-8-sig')
        write_json(complete / 'input-hashes.json', records)
        (complete / 'README.txt').write_text('Completed Kinetic Tech video\n\ncompleted.mp4: final video with voice, native effects, music and first-frame cover.\ncover.png / cover.jpg: separate publishing cover images.\ncaptions.srt: supplied sentence-level captions; no new ASR timing was invented.\nqa/verification.json and qa/contact.jpg: automated checks and visual review contact sheet.\n\nAutomated checks passed. Inspect the image/contact sheet and listen to the final video before publication.\nA first-frame cover does not set a social platform publishing cover automatically.\nMusic source records are not a copyright permission guarantee.\n', encoding='utf-8')
        delivery_files = ['completed.mp4', 'cover.png', 'cover.jpg', 'cover-provenance.json', 'captions.srt', 'music-selection.json', 'qa/verification.json', 'qa/contact.jpg']
        write_json(complete / 'delivery-manifest.json', {'status': 'automated_checks_passed', 'human_review': 'required before publication',
                   'files': [{'path': name, 'sha256': sha(complete / name), 'bytes': (complete / name).stat().st_size} for name in delivery_files]})
        state['status'] = 'complete'
        state['delivery'] = str(complete)
        state['completed_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(state_file, state)
        print(json.dumps({'status': 'complete', 'delivery': str(complete), 'video': str(complete / 'completed.mp4'), 'review': str(complete / 'qa/contact.jpg')}, ensure_ascii=False), flush=True)
    except BaseException as error:
        state['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
        state['error'] = str(error)
        for stage_row in state['stages']:
            if stage_row['status'] == 'running':
                stage_row['status'] = state['status']
        write_json(state_file, state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    default_work = Path(os.environ.get('KINETIC_RUNTIME_HOME', ROOT.parent / '.kinetic-tech-runtime'))
    for name in ['run', 'validate']:
        command = commands.add_parser(name)
        command.add_argument('--job', required=True, type=Path)
        command.add_argument('--work', type=Path, default=default_work)
        command.add_argument('--bootstrap', action='store_true', help='Prepare declared runtime dependencies when needed.')
        if name == 'run':
            command.add_argument('--out', required=True, type=Path, help='A new directory; existing runs are not overwritten or silently resumed.')
    args = parser.parse_args()
    args.job = file_path(str(args.job), Path.cwd())
    if args.command == 'run' and args.out.expanduser().exists():
        raise FileExistsError('Output already exists. Choose a new --out directory; existing logs and media are preserved.')
    work = args.work.expanduser().resolve()
    config = load_runtime(work, args.bootstrap)
    env = environment(work, config)
    job, normalized, records = prepare_inputs(args.job, config, env)
    if args.command == 'validate':
        print(json.dumps({'status': 'input_schema_and_files_valid', 'inputs': records,
                          'limits': 'Native semantic plan, media lengths, rendering, and encoded audio are checked during run.'}, ensure_ascii=False))
        return
    run_job(args, work, config, env, job, normalized, records)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted; partial outputs and stage status are preserved. Inspect the previous run and use a new output directory.', file=sys.stderr)
        raise SystemExit(130)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as error:
        print('Workflow failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
