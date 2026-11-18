#!/usr/bin/env node
// Reuse the native B1 composition without modifying the prepared instance.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {once} from 'node:events';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const repository = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const defaultWork = path.join(path.dirname(repository), '.kinetic-tech-runtime');
const help = `Usage: node render_cover.mjs --instance DIR --out DIR --title TEXT --presenter-frame FILE [options]

Render the approved native Kinetic Tech landscape cover (1920x1080).
Required:
  --instance DIR             A prepared native template instance
  --out DIR                  Output directory; existing cover files are preserved
  --title TEXT               Topic-specific single-line title (required)
  --presenter-frame FILE     JPG/PNG/WebP; absolute or relative to the instance
Options:
  --label TEXT               Small upper-left topic label (default: empty)
  --subtitle TEXT            One or two lines; literal \\n is accepted (default: empty)
  --footer TEXT              Gold lower-left line (default: empty)
  --chrome FILE             Chrome executable; also reads CHROME
  --work DIR                Bootstrap runtime directory; also reads KINETIC_RUNTIME_HOME
                            (default: .kinetic-tech-runtime next to the repository)
  --playwright-root DIR      Directory containing node_modules/playwright-core
                            (default: template path in the runtime's runtime.json)
  --temp-dir DIR             Browser temporary files (default: runtime/temp/cover)
  --help                    Show this help

Outputs: cover.png, cover.jpg, cover-provenance.json.
The script exports a still cover only; the final video assembly handles first-frame insertion.
Long text is rejected rather than cropped. Shorten/rewrite it and retry in a new output directory.
`;

function parseArgs(args) {
  const keys = new Set(['instance', 'out', 'title', 'label', 'subtitle', 'footer', 'presenter-frame', 'chrome', 'work', 'playwright-root', 'temp-dir']);
  const options = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--help' || args[i] === '-h') return {help: true};
    const key = args[i].startsWith('--') ? args[i].slice(2) : '';
    if (!keys.has(key)) throw Error(`Unknown argument: ${args[i]}. Use --help.`);
    if (Object.hasOwn(options, key)) throw Error(`Repeated argument: --${key}`);
    if (i + 1 >= args.length || args[i + 1].startsWith('--')) throw Error(`Missing value: --${key}`);
    options[key] = args[++i];
  }
  for (const key of ['instance', 'out', 'title', 'presenter-frame']) {
    if (!options[key]?.trim()) throw Error(`Required: --${key}. Use --help.`);
  }
  return options;
}

function assertFile(file, description) {
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) throw Error(`${description} not found: ${file}`);
}

function singleLine(value, name) {
  if (/[\r\n\t]/.test(value)) throw Error(`${name} must be a single line without tabs.`);
  if ([...value].length > 100) throw Error(`${name} is too long for this cover; shorten it.`);
  return value;
}

function findChrome(explicit) {
  const candidates = [explicit, process.env.CHROME,
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Google/Chrome/Application/chrome.exe'),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Google/Chrome/Application/chrome.exe'),
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium'];
  if (explicit) { assertFile(path.resolve(explicit), 'Chrome'); return path.resolve(explicit); }
  const found = candidates.find(p => p && fs.existsSync(p));
  if (!found) throw Error('Chrome not found. Pass --chrome with an installed Chrome executable.');
  return found;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) { console.log(help); return; }
  const root = fs.realpathSync(path.resolve(options.instance));
  const out = path.resolve(options.out);
  const destinations = ['cover.png', 'cover.jpg', 'cover-provenance.json'].map(name => path.join(out, name));
  for (const file of destinations) if (fs.existsSync(file)) throw Error(`Preserve existing output: ${file}`);
  for (const name of ['settings.json', 'index.html', 'basic.js']) assertFile(path.join(root, name), 'Prepared instance file');
  const presenterPath = fs.realpathSync(path.resolve(root, options['presenter-frame']));
  assertFile(presenterPath, 'Presenter image');
  const presenterExt = path.extname(presenterPath).toLowerCase();
  if (!['.jpg', '.jpeg', '.png', '.webp'].includes(presenterExt)) throw Error('Presenter frame must be a JPG, PNG, or WebP image.');
  const title = singleLine(options.title.trim(), 'Title');
  const label = singleLine(options.label || '', 'Label');
  const footer = singleLine(options.footer || '', 'Footer');
  const subtitle = (options.subtitle || '').replaceAll('\\n', '\n').replaceAll('\r\n', '\n');
  if (subtitle.split('\n').length > 2 || /[\r\t]/.test(subtitle) || [...subtitle].length > 120) {
    throw Error('Subtitle must have at most two explicit short lines without tabs.');
  }
  const runtimeRoot = path.resolve(options.work || process.env.KINETIC_RUNTIME_HOME || defaultWork);
  const runtimeFile = path.join(runtimeRoot, 'runtime.json');
  const runtime = fs.existsSync(runtimeFile) ? JSON.parse(fs.readFileSync(runtimeFile, 'utf8').replace(/^\uFEFF/, '')) : {};
  const chrome = findChrome(options.chrome || process.env.CHROME || runtime.chrome);
  const dependencyRoot = options['playwright-root'] || process.env.KINETIC_PLAYWRIGHT_ROOT || runtime.template;
  if (!dependencyRoot) throw Error(`Runtime not configured at ${runtimeFile}. Run runtime.py bootstrap first, pass --work for a custom runtime, or provide --playwright-root.`);
  const playwrightRoot = path.resolve(dependencyRoot);
  const require = createRequire(path.join(playwrightRoot, 'package.json'));
  let chromium;
  try { ({chromium} = require('playwright-core')); }
  catch { throw Error(`playwright-core is not installed under ${playwrightRoot}; run the skill setup or pass --playwright-root.`); }
  const temporary = path.resolve(options['temp-dir'] || path.join(runtimeRoot, 'temp', 'cover'));
  fs.mkdirSync(temporary, {recursive: true});
  process.env.TEMP = process.env.TMP = process.env.TMPDIR = temporary;

  const settings = JSON.parse(fs.readFileSync(path.join(root, 'settings.json'), 'utf8').replace(/^\uFEFF/, ''));
  if (settings.layout && settings.layout !== 'landscape') throw Error('This renderer supports the approved native landscape layout only.');
  settings.selected = ['B1']; settings.duration = 8; settings.captions = []; settings.markWindows = [];
  settings.plan = [{id: 'B1', title: '', sourceStart: 250, sourceEnd: 258, outputStart: 0, outputEnd: 8}];
  settings.titles = {B1: ''}; settings.language = 'zh';
  settings.basic = {label, keyword: title, explanation: subtitle};
  const presenterUrl = '/user-assets/__cover-presenter' + presenterExt;
  settings.presenter = {...settings.presenter, mode: 'image', file: presenterUrl.slice(1), tracking: []};
  settings.media = {...settings.media, presenter: settings.presenter};
  const mime = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'};
  const server = http.createServer((request, response) => {
    try {
      if (request.method !== 'GET') { response.writeHead(405).end(); return; }
      const url = new URL(request.url, 'http://127.0.0.1');
      if (url.pathname === '/favicon.ico') { response.writeHead(204).end(); return; }
      if (url.pathname === '/user-input.js') {
        response.setHeader('Content-Type', 'text/javascript');
        response.end('window.KINETIC_INPUT=' + JSON.stringify(settings) + ';'); return;
      }
      let file;
      if (url.pathname === presenterUrl) file = presenterPath;
      else {
        file = fs.realpathSync(path.resolve(root, '.' + decodeURIComponent(url.pathname)));
        const relative = path.relative(root, file);
        if (relative.startsWith('..' + path.sep) || relative === '..' || path.isAbsolute(relative)) { response.writeHead(404).end(); return; }
      }
      if (!fs.statSync(file).isFile()) { response.writeHead(404).end(); return; }
      response.setHeader('Content-Type', mime[path.extname(file).toLowerCase()] || 'application/octet-stream');
      const stream = fs.createReadStream(file);
      stream.on('error', () => response.destroy()); stream.pipe(response);
    } catch { response.writeHead(404).end(); }
  });
  let browser;
  const errors = [];
  try {
    server.listen(0, '127.0.0.1'); await once(server, 'listening');
    browser = await chromium.launch({headless: true, executablePath: chrome, timeout: 30000, args: ['--force-color-profile=srgb', '--disable-gpu']});
    const page = await browser.newPage({viewport: {width: 1920, height: 1080}, deviceScaleFactor: 1});
    page.on('pageerror', error => errors.push(error.message));
    page.on('requestfailed', request => errors.push(`Failed asset: ${request.url()} (${request.failure()?.errorText})`));
    page.on('response', response => { if (response.status() >= 400) errors.push(`Missing asset: ${response.status()} ${response.url()}`); });
    const origin = `http://127.0.0.1:${server.address().port}`;
    await page.route('**/*', route => {
      if (route.request().url().startsWith(origin + '/') || route.request().url().startsWith('data:')) return route.continue();
      return route.abort();
    });
    await page.goto(origin + '/index.html', {timeout: 30000});
    await page.evaluate(async () => {
      await Promise.race([
        (async () => { await window.CONSUMER_READY; await document.fonts.ready; await renderAt(3); })(),
        new Promise((_, reject) => setTimeout(() => reject(Error('Native cover render timed out after 30 seconds')), 30000)),
      ]);
    });
    const layout = await page.evaluate(({label, footer}) => {
      const style = document.createElement('style');
      style.textContent = '#chrome,#ov,#tkL .lab{display:none!important}'; document.head.append(style);
      const canvas = document.createElement('canvas').getContext('2d');
      const measure = (text, font, spacing) => { canvas.font = font; return canvas.measureText(text).width + [...text].length * spacing; };
      const labelWidth = measure(label, '500 22px "Geist Mono",PuHuiTi,sans-serif', 4);
      const footerWidth = measure(footer, '650 35px PuHuiTi,sans-serif', 2);
      if (labelWidth > 940) throw Error(`Label exceeds its 940px area (${Math.round(labelWidth)}px). Shorten it.`);
      if (footerWidth > 940) throw Error(`Footer exceeds its 940px area (${Math.round(footerWidth)}px). Shorten it.`);
      if (footer) {
        const line = document.createElement('div'); line.textContent = footer;
        line.style.cssText = 'position:absolute;left:190px;top:825px;white-space:pre;font:650 35px PuHuiTi,sans-serif;letter-spacing:2px;color:#f2c85a';
        document.getElementById('stage').append(line);
      }
      return {labelWidth, footerWidth, textAreaWidth: 940};
    }, {label, footer});
    if (errors.length) throw Error(errors.join('\n'));
    const png = await page.screenshot({type: 'png'});
    const jpg = await page.screenshot({type: 'jpeg', quality: 96});
    const provenance = {
      title, label, subtitle, footer, width: 1920, height: 1080,
      presenterSource: presenterPath,
      presenterSha256: crypto.createHash('sha256').update(fs.readFileSync(presenterPath)).digest('hex'),
      instance: root, template: 'kinetic-tech v0.2.7-open-beta / B1', renderTime: 3,
      method: 'Native composition with topic-specific text and original presenter frame; subtitle, timecode and technical labels hidden for cover only',
      layout, errors,
    };
    fs.mkdirSync(out, {recursive: true});
    const created = [];
    try {
      for (const [file, bytes] of [[destinations[0], png], [destinations[1], jpg], [destinations[2], JSON.stringify(provenance, null, 2) + '\n']]) {
        fs.writeFileSync(file, bytes, {flag: 'wx'}); created.push(file);
      }
    } catch (error) { for (const file of created) fs.unlinkSync(file); throw error; }
    console.log(JSON.stringify({png: destinations[0], jpg: destinations[1], provenance: destinations[2], width: 1920, height: 1080, errors}, null, 2));
  } finally {
    await browser?.close().catch(() => {});
    if (server.listening) await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
