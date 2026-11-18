"""Resolve declared tools and run the real template in a separate writable runtime."""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request

SKILL = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL / 'assets/template'
DEFAULT_WORK = Path(os.environ.get('KINETIC_RUNTIME_HOME', SKILL.parent / '.kinetic-tech-runtime'))
EXPECTED = dict(line.strip().split('==') for line in (SKILL / 'requirements.txt').read_text().splitlines() if line.strip())

def run(command, **kwargs):
    return subprocess.run([str(v) for v in command], check=True, **kwargs)

def first_file(candidates):
    return next((str(Path(x).resolve()) for x in candidates if x and Path(x).is_file()), None)

def selected_file(explicit, variable, candidates):
    requested = explicit or os.environ.get(variable)
    if requested:
        result = first_file([requested, shutil.which(requested)])
        if not result:
            raise RuntimeError(f'{variable}: executable does not exist: {requested}')
        return result
    return first_file(candidates)

def discover(a):
    local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    state_file = a.work.resolve() / 'runtime.json'
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.is_file() else {}
    python = selected_file(a.python, 'KINETIC_PYTHON', [
        a.work.resolve() / ('python/Scripts/python.exe' if os.name == 'nt' else 'python/bin/python'),
        state.get('python'), sys.executable, shutil.which('python3'), shutil.which('python')])
    node = selected_file(a.node, 'KINETIC_NODE', [state.get('node'), shutil.which('node')])
    ffmpeg = selected_file(a.ffmpeg, 'KINETIC_FFMPEG', [state.get('ffmpeg'), shutil.which('ffmpeg')])
    ffprobe = selected_file(a.ffprobe, 'KINETIC_FFPROBE', [
        Path(ffmpeg).with_name('ffprobe.exe' if os.name == 'nt' else 'ffprobe') if ffmpeg else None,
        state.get('ffprobe'), shutil.which('ffprobe')])
    chrome = selected_file(a.chrome, 'CHROME', [state.get('chrome'),
        shutil.which('google-chrome'), shutil.which('google-chrome-stable'), shutil.which('chromium'),
        shutil.which('chromium-browser'), shutil.which('chrome'), shutil.which('msedge'),
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
        local / 'Google/Chrome/Application/chrome.exe',
        Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
        Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge')])
    return {'python': python, 'node': node, 'ffmpeg': ffmpeg, 'ffprobe': ffprobe, 'chrome': chrome}

def environment(work, config):
    env = os.environ.copy()
    paths = list(dict.fromkeys(str(Path(config[k]).parent) for k in ('node', 'ffmpeg', 'ffprobe') if config.get(k)))
    env['PATH'] = os.pathsep.join(paths + [env.get('PATH', '')])
    for name, part in {'TEMP': 'temp', 'TMP': 'temp', 'TMPDIR': 'temp', 'PIP_CACHE_DIR': 'cache/pip',
                       'UV_CACHE_DIR': 'cache/uv', 'npm_config_cache': 'cache/npm',
                       'PLAYWRIGHT_BROWSERS_PATH': 'cache/browsers'}.items():
        env[name] = str(work / part)
        (work / part).mkdir(parents=True, exist_ok=True)
    env['PYTHONUTF8'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    if config.get('chrome'):
        env['CHROME'] = config['chrome']
    return env

def python_info(python):
    if not python:
        return {'ok': False, 'error': 'Python not found'}
    code = 'import sys,json,importlib.metadata as m\nnames=' + repr(list(EXPECTED)) + '''
packages={}
for name in names:
    try: packages[name]=m.version(name)
    except m.PackageNotFoundError: packages[name]=None
print(json.dumps({"python":list(sys.version_info[:3]),"packages":packages}))
'''
    result = subprocess.run([python, '-c', code], capture_output=True, text=True, encoding='utf-8', timeout=30)
    if result.returncode:
        return {'ok': False, 'error': result.stderr.strip().splitlines()[-1] if result.stderr else 'Probe failed'}
    result = json.loads(result.stdout)
    result['minimum_python'] = [3, 12]
    result['version_ok'] = tuple(result['python']) >= (3, 12)
    result['ok'] = result['version_ok'] and result['packages'] == EXPECTED
    return result

def tools_info(config):
    report = {}
    for key, arguments in [('node', ['--version']), ('ffmpeg', ['-version']), ('ffprobe', ['-version'])]:
        executable = config.get(key)
        if not executable or not Path(executable).is_file():
            report[key] = {'ok': False, 'error': 'Executable not found'}
            continue
        result = subprocess.run([executable, *arguments], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        line = (result.stdout or result.stderr).strip().splitlines()
        report[key] = {'ok': result.returncode == 0, 'version': line[0] if line else ''}
        if key == 'node':
            match = re.match(r'v?(\d+)\.', report[key]['version'])
            report[key]['ok'] = result.returncode == 0 and bool(match and int(match[1]) >= 22)
            report[key]['minimum_major'] = 22
    report['chrome'] = {'ok': bool(config.get('chrome') and Path(config['chrome']).is_file()),
                        'check': 'executable exists; headless rendering is checked by preview/demo'}
    if report['ffmpeg']['ok']:
        for flag, names in [('-filters', ['colorspace', 'alimiter', 'overlay']), ('-encoders', ['libx264', 'aac'])]:
            result = subprocess.run([config['ffmpeg'], '-hide_banner', flag], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            missing = [name for name in names if not re.search(r'\b' + name + r'\b', result.stdout)]
            report['ffmpeg'].setdefault('missing_capabilities', []).extend(missing)
            report['ffmpeg']['ok'] &= result.returncode == 0 and not missing
    return report

def runtime_info(work, config):
    state_file = work / 'runtime.json'
    info = {'tools': config, 'tool_checks': tools_info(config), 'python': python_info(config.get('python')),
            'work': str(work), 'runtime_ready': False, 'template_bundled': TEMPLATE.is_dir()}
    if state_file.is_file():
        state = json.loads(state_file.read_text(encoding='utf-8'))
        target = Path(state.get('template', work / 'template'))
        expected_version = json.loads((TEMPLATE / 'package-lock.json').read_text())['packages']['node_modules/playwright-core']['version']
        info['configured_runtime'] = state
        info['configured_playwright'] = pw_version(target)
        info['template_digest_matches'] = bool(target.is_dir() and state.get('template_digest') == source_digest(TEMPLATE) == source_digest(target))
        info['runtime_ready'] = bool(info['python']['ok'] and all(item['ok'] for item in info['tool_checks'].values()) and info['template_digest_matches'] and info['configured_playwright'] == expected_version)
    return info

def source_digest(root):
    digest = hashlib.sha256()
    for file in sorted(p for p in root.rglob('*') if p.is_file() and not {'node_modules', '__pycache__'} & set(p.parts)):
        digest.update(file.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    return digest.hexdigest()

def pw_version(root):
    file = root / 'node_modules/playwright-core/package.json'
    try:
        return json.loads(file.read_text())['version']
    except (OSError, ValueError, KeyError):
        return None

def bootstrap(a, work, config):
    if not all(config.get(k) for k in ('python', 'node', 'ffmpeg', 'ffprobe', 'chrome')):
        raise RuntimeError('Missing system tools; run doctor and provide --python/--node/--ffmpeg/--ffprobe/--chrome. No browser or FFmpeg is downloaded automatically.')
    checks = tools_info(config)
    if not all(item['ok'] for item in checks.values()):
        raise RuntimeError('System tool requirements are not satisfied: ' + json.dumps(checks))
    if not python_info(config['python']).get('version_ok'):
        raise RuntimeError('This pinned runtime requires Python >= 3.12 (NumPy and SciPy metadata). Provide --python pointing to a compatible interpreter.')
    env = environment(work, config)
    state_file = work / 'runtime.json'
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding='utf-8'))
        if state.get('template_digest') != source_digest(TEMPLATE):
            raise RuntimeError('This work directory belongs to another template revision; use a new --work directory.')
    if not python_info(config['python'])['ok']:
        candidates = [work / 'python/Scripts/python.exe', work / 'python/bin/python']
        found = next((str(p) for p in candidates if p.is_file() and python_info(str(p))['ok']), None)
        if found:
            config['python'] = found
        else:
            if a.offline:
                raise RuntimeError('Pinned Python dependencies not available offline; run bootstrap without --offline or provide --python.')
            venv = work / 'python'
            if not venv.exists():
                run([config['python'], '-m', 'venv', venv], env=env)
            config['python'] = str(venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
            run([config['python'], '-m', 'pip', 'install', '--disable-pip-version-check', '-r', SKILL / 'requirements.txt'], env=env)
    if not python_info(config['python'])['ok']:
        raise RuntimeError('Pinned Python versions are not satisfied')
    target = work / 'template'
    if target.exists():
        if source_digest(target) != source_digest(TEMPLATE):
            raise RuntimeError('Existing template work copy changed; preserve it and choose another --work directory.')
    else:
        shutil.copytree(TEMPLATE, target)
    lock = json.loads((target / 'package-lock.json').read_text())['packages']['node_modules/playwright-core']
    version = lock['version']
    if pw_version(target) != version:
        destination = target / 'node_modules/playwright-core'
        if destination.exists():
            raise RuntimeError('Existing Playwright dependency differs from lock; preserve it and use a new --work directory.')
        configured = os.environ.get('KINETIC_PLAYWRIGHT_ROOT')
        roots = [Path(configured)] if configured else []
        available = next((r for r in roots if pw_version(r) == version), None)
        if available:
            shutil.copytree(available / 'node_modules/playwright-core', destination)
            method = 'copied existing installed dependency with matching locked version'
        else:
            if a.offline:
                raise RuntimeError('Locked Playwright not available offline; supply KINETIC_PLAYWRIGHT_ROOT or bootstrap without --offline.')
            archive = work / 'cache' / ('playwright-core-' + version + '.tgz')
            archive.parent.mkdir(exist_ok=True)
            with urllib.request.urlopen(lock['resolved'], timeout=60) as response:
                data = response.read()
            expected = lock['integrity'].removeprefix('sha512-')
            if base64.b64encode(hashlib.sha512(data).digest()).decode() != expected:
                raise RuntimeError('Playwright download failed SHA512 integrity verification')
            archive.write_bytes(data)
            destination.mkdir(parents=True)
            with tarfile.open(archive) as tf:
                for member in tf.getmembers():
                    parts = Path(member.name).parts
                    if not parts or parts[0] != 'package' or member.issym() or member.islnk():
                        raise RuntimeError('Unexpected archive path or link')
                    if len(parts) == 1:
                        continue
                    relative = Path(*parts[1:])
                    output = (destination / relative).resolve()
                    if not output.is_relative_to(destination.resolve()):
                        raise RuntimeError('Archive path escapes dependency root')
                    if member.isdir():
                        output.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with tf.extractfile(member) as stream, output.open('xb') as out:
                            shutil.copyfileobj(stream, out)
            method = 'downloaded exact lock URL and verified SHA512; no package lifecycle scripts'
    else:
        method = 'existing matching locked version'
    run([config['node'], '-e', "const p=require('playwright-core/package.json'); console.log('playwright-core '+p.version)"], cwd=target, env=env)
    state = {**config, 'work': str(work), 'template': str(target), 'template_digest': source_digest(TEMPLATE),
             'python_packages': EXPECTED, 'playwright_version': version, 'playwright_setup': method}
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return state

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK)
    for name in ('python', 'node', 'ffmpeg', 'ffprobe', 'chrome'):
        parser.add_argument('--' + name, help='Explicit executable; otherwise discover local tools')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor', help='Report tools and dependency status without installation')
    setup = commands.add_parser('bootstrap', help='Prepare an isolated writable runtime and exact declared dependencies')
    setup.add_argument('--offline', action='store_true', help='Do not download missing dependencies')
    template = commands.add_parser('template', help='Forward arguments to the original template adapter')
    template.add_argument('arguments', nargs=argparse.REMAINDER)
    a = parser.parse_args()
    work = a.work.resolve()
    if work == SKILL or work.is_relative_to(SKILL):
        parser.error('--work must be outside the installed skill')
    config = discover(a)
    state_file = work / 'runtime.json'
    if a.command == 'doctor':
        report = runtime_info(work, config)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report['runtime_ready'] else 1)
    if a.command == 'bootstrap':
        print(json.dumps(bootstrap(a, work, config), ensure_ascii=False, indent=2))
        return
    if not state_file.is_file():
        parser.error('Run bootstrap for this --work directory first')
    state = json.loads(state_file.read_text(encoding='utf-8'))
    if state.get('template_digest') != source_digest(TEMPLATE) or source_digest(Path(state['template'])) != state['template_digest']:
        parser.error('Template revision changed; choose a new --work directory and bootstrap')
    for key in ('python', 'node', 'ffmpeg', 'ffprobe', 'chrome'):
        if getattr(a, key):
            state[key] = str(Path(getattr(a, key)).resolve())
    arguments = a.arguments[1:] if a.arguments[:1] == ['--'] else a.arguments
    if not arguments:
        parser.error('template requires plan|prepare|preview|events|render and adapter arguments')
    raise SystemExit(run([state['python'], Path(state['template']) / 'adapter.py', *arguments],
                         cwd=work, env=environment(work, state)).returncode)

if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print('Runtime setup failed: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
