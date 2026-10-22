#!/usr/bin/env python3
"""Inspect released SQLite databases, freeze a historical cohort, and set up dependencies."""
import argparse
import csv
import hashlib
import io
import json
import os
import platform
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent / 'data'
UPSTREAM = ROOT / 'upstream'
COMMIT = 'a4f391d604e5cd557b881145b2a1cfd072e542d0'
SEED = 42
COUNT = 500
GIB = 1024 ** 3
RESERVE_BYTES = 10 * GIB
PYTHON_PACKAGES = ['beautifulsoup4==4.13.4', 'zstandard==0.23.0']
PLOT_PACKAGES = ['matplotlib==3.11.2', 'scipy==1.18.1']
FORM_TYPES = {'Account Registration Form', 'Account Login Form', 'Account Recovery Form',
              'Payment Form', 'Role Application Form', 'Financial Application Form',
              'Subscription Form', 'Reservation Form', 'Contact Form', 'Content Submission Form', 'Unknown'}
PI_TYPES = {'Address', 'DateOfBirth', 'EmailAddress', 'Ethnicity', 'Fingerprints', 'Gender',
            'GovernmentId', 'LocationCityOrCoarser', 'BankAccountNumber', 'PersonName', 'PhoneNumber',
            'PostalCode', 'UsernameOrOtherId', 'TaxId', 'Password', 'AgeOrAgeGroup',
            'CitizenshipOrImmigrationStatus', 'BusinessInfo', 'MilitaryStatus'}
FORM_QUERY = '''SELECT a.domain, a.form_type, b.field_list
FROM form_classification a INNER JOIN field_classification b
USING (domain, job_hash, form_filename)'''
SITE_QUERY = '''SELECT t.domain, t.ranking, d.content_categories, h.url
FROM tranco_list t INNER JOIN domain_info d USING (domain)
INNER JOIN http_info h USING (domain) ORDER BY t.domain'''


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024 ** 2), b''):
            h.update(b)
    return h.hexdigest()


def connect(path):
    path = Path(path).resolve(strict=True)
    con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    con.execute('PRAGMA query_only=ON')
    return con


def schemas(con):
    return {name: [r[1] for r in con.execute(f'PRAGMA table_info("{name.replace(chr(34), chr(34)*2)}")')]
            for name, in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def require(con, expected):
    actual = schemas(con)
    for table, columns in expected.items():
        missing = set(columns) - set(actual.get(table, []))
        if missing:
            raise ValueError(f'{table} missing columns {sorted(missing)}. Run inspect and check the released schema.')


def eligible(domain_db, annotation_db):
    rejected = {'invalid_annotations': 0, 'invalid_categories': 0, 'invalid_start_url': 0, 'no_usable_annotations': 0}
    with connect(annotation_db) as con:
        require(con, {'form_classification': ['domain', 'job_hash', 'form_filename', 'form_type'],
                      'field_classification': ['domain', 'job_hash', 'form_filename', 'field_list']})
        observed = set()
        for domain, purpose, raw in con.execute(FORM_QUERY):
            try:
                labels = json.loads(raw)
                valid = isinstance(labels, list) and labels and all(isinstance(x, str) and x in PI_TYPES for x in labels)
            except (ValueError, TypeError):
                valid = False
            if purpose in FORM_TYPES and valid:
                observed.add(domain)
            else:
                rejected['invalid_annotations'] += 1
    rows = []
    with connect(domain_db) as con:
        require(con, {'tranco_list': ['domain', 'ranking'], 'domain_info': ['domain', 'content_categories'],
                      'http_info': ['domain', 'url']})
        for domain, rank, raw, url in con.execute(SITE_QUERY):
            if domain not in observed:
                rejected['no_usable_annotations'] += 1
                continue
            try:
                categories = json.loads(raw)
                if not isinstance(categories, list) or not all(isinstance(c, dict) and 'id' in c and isinstance(c.get('name'), str) for c in categories):
                    raise ValueError('category mapping is not a list of id/name objects')
            except (ValueError, TypeError):
                rejected['invalid_categories'] += 1
                continue
            try:
                parts = urlsplit(url or '')
                valid_url = parts.scheme in {'http', 'https'} and parts.hostname and not parts.username and not parts.password
            except (ValueError, TypeError):
                valid_url = False
            if not valid_url:
                rejected['invalid_start_url'] += 1
                continue
            rows.append({'domain': domain, 'rank': rank, 'categories': json.dumps(categories, separators=(',', ':'), sort_keys=True), 'start_url': url})
    if len({r['domain'] for r in rows}) != len(rows):
        raise ValueError('Database join produced duplicate domains; inspect the actual uniqueness constraints.')
    return sorted(rows, key=lambda r: r['domain']), rejected


def category_names(domain_db):
    names = {'-1': 'Unknown'}
    with connect(domain_db) as con:
        require(con, {'domain_info': ['content_categories']})
        for raw, in con.execute('SELECT content_categories FROM domain_info'):
            try:
                values = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, dict) and 'id' in value and isinstance(value.get('name'), str):
                    key = str(value['id'])
                    if key in names and names[key] != value['name']:
                        raise ValueError(f'Conflicting historical category names for ID {key}')
                    names[key] = value['name']
    return names


def select(args):
    started = time.monotonic()
    rows, rejected = eligible(args.domain_db, args.annotation_db)
    if len(rows) < args.count:
        raise ValueError(f'Only {len(rows)} eligible domains, need {args.count}. Rejections: {rejected}')
    sample = sorted(random.Random(args.seed).sample(rows, args.count), key=lambda r: r['domain'])
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=['domain', 'rank', 'categories', 'start_url'])
    writer.writeheader()
    writer.writerows(sample)
    content = buf.getvalue().encode()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    sites = out / 'sites.csv'
    manifest_path = out / 'manifest.json'
    checksums = {str(Path(p).resolve()): {'sha256': sha256(p), 'bytes': Path(p).stat().st_size}
                 for p in [args.domain_db, args.annotation_db]}
    manifest = {'upstream_commit': COMMIT, 'seed': args.seed, 'count': args.count,
                'eligible_count': len(rows), 'databases': checksums, 'selection_sql': [FORM_QUERY, SITE_QUERY],
                'selection_rule': 'Joined historical form/field record with recognized form_type and nonempty JSON labels drawn from the 19 source PI classes; historical rank, valid category JSON and HTTP starting URL. Empty categories retain historical Unknown. Sort eligible domains, random.Random(seed).sample, sort output.',
                'category_names': category_names(args.domain_db),
                'rejected_records': rejected, 'sites_sha256': hashlib.sha256(content).hexdigest()}
    if sites.exists():
        if sites.read_bytes() != content or not manifest_path.exists():
            raise ValueError('Existing cohort differs or has no manifest. Preserve it and choose another output directory.')
        previous = json.loads(manifest_path.read_text())
        if previous != manifest:
            raise ValueError('Existing manifest differs. Preserve the fixed cohort and investigate the changed input.')
        print(f'Reused {sites}, {len(sample)} sites, {time.monotonic()-started:.2f} seconds')
        return
    sites.write_bytes(content)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Wrote {sites}, {len(sample)} of {len(rows)} eligible sites, {time.monotonic()-started:.2f} seconds')


def inspect(args):
    result = {}
    for path in [args.domain_db, args.annotation_db]:
        with connect(path) as con:
            tables = schemas(con)
            details = {}
            for name in tables:
                quoted = name.replace(chr(34), chr(34) * 2)
                columns = [{'position': r[0], 'name': r[1], 'type': r[2], 'not_null': bool(r[3]), 'default': r[4], 'primary_key_position': r[5]}
                           for r in con.execute(f'PRAGMA table_info("{quoted}")')]
                indexes = []
                for row in con.execute(f'PRAGMA index_list("{quoted}")'):
                    index_name = row[1].replace(chr(34), chr(34) * 2)
                    indexes.append({'name': row[1], 'unique': bool(row[2]), 'origin': row[3],
                                    'columns': [r[2] for r in con.execute(f'PRAGMA index_info("{index_name}")')]})
                details[name] = {'columns': columns, 'indexes': indexes,
                                 'row_count': con.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]}
            result[str(Path(path).resolve())] = {'bytes': Path(path).stat().st_size, 'tables': tables, 'table_details': details}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({path: {'bytes': value['bytes'], 'tables': value['tables']} for path, value in result.items()}, indent=2))
    print(f'Saved schema details to {args.output}')


def tree_bytes(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file() and not p.is_symlink()) if Path(path).exists() else 0


def run(command, cwd=None, env=None):
    subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True)


def setup(args):
    started = time.monotonic()
    if args.warm_navigation and args.skip_compile:
        raise ValueError('--warm-navigation requires compilation; omit --skip-compile')
    actual = subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != COMMIT:
        raise ValueError(f'Upstream HEAD {actual} differs from pinned {COMMIT}')
    apply_crawler_patch()
    if shutil.disk_usage(ROOT).free < 4 * GIB + RESERVE_BYTES:
        raise ValueError('Setup needs 4 GiB free plus the 10 GiB crawl reserve.')
    python = ROOT / '.venv/bin/python'
    if not python.exists():
        run([sys.executable, '-m', 'venv', ROOT / '.venv'])
    run([python, '-m', 'pip', 'install', '--cache-dir', ROOT / '.pip-cache', *PYTHON_PACKAGES, *PLOT_PACKAGES])
    crawler = UPSTREAM / 'crawler'
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(ROOT / '.browsers'))
    run(['npm', 'ci', '--cache', str(ROOT / '.npm-cache')], cwd=crawler, env=env)
    run(['npx', 'playwright', 'install', 'chromium'], cwd=crawler, env=env)
    if not args.skip_compile:
        run(['npm', 'run', 'compile'], cwd=crawler, env=env)
    versions = json.loads(subprocess.check_output(['npm', 'ls', '--depth=0', '--json'], cwd=crawler, text=True))
    result = {'elapsed_seconds': round(time.monotonic()-started, 3), 'upstream_commit': actual,
              'node': subprocess.check_output(['node', '--version'], text=True).strip(),
              'architecture': platform.machine(),
              'python_packages': subprocess.check_output([str(python), '-m', 'pip', 'freeze'], text=True).splitlines(),
              'npm': versions, 'compiled': not args.skip_compile,
              'browser_path': str(ROOT / '.browsers'),
              'sizes_bytes': {'.venv': tree_bytes(ROOT / '.venv'), 'node_modules': tree_bytes(crawler / 'node_modules'), '.browsers': tree_bytes(ROOT / '.browsers'), 'navigation_model_cache': tree_bytes(ROOT / '02-crawl/data/navigation-model-cache')},
              'free_bytes_after': shutil.disk_usage(ROOT).free}
    DATA.mkdir(exist_ok=True)
    (DATA / 'setup.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['elapsed_seconds', 'compiled', 'sizes_bytes', 'free_bytes_after']}, indent=2))
    if args.warm_navigation:
        warm_navigation()


def apply_crawler_patch():
    patch = ROOT / '02-crawl/data/crawler.patch'
    if not patch.exists():
        raise ValueError(f'Missing saved crawler patch {patch}. Restore the tracked patch before compiling.')
    reverse = subprocess.run(['git', '-C', str(UPSTREAM), 'apply', '--reverse', '--check', str(patch)], capture_output=True)
    if reverse.returncode == 0:
        return
    run(['git', '-C', UPSTREAM, 'apply', '--check', patch])
    run(['git', '-C', UPSTREAM, 'apply', patch])


def warm_navigation():
    """One CPU process, shared cache, quantized ONNX only, bounded downloads."""
    cache = ROOT / '02-crawl/data/navigation-model-cache'
    report = DATA / 'navigation-model.json'
    script = r'''
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { performance } from 'node:perf_hooks';
const originalFetch = globalThis.fetch;
let downloaded = 0;
const cap = 40 * 1024 * 1024;
globalThis.fetch = async (url, options = {}) => {
  const text = String(url);
  if (text.includes('/resolve/') && text.endsWith('.onnx') && !text.endsWith('/model_quantized.onnx')) {
    throw Error('Refusing non-quantized navigation weights');
  }
  const response = await originalFetch(url, {...options, signal: AbortSignal.timeout(60000)});
  const length = Number(response.headers.get('content-length') || 0);
  if (length > cap - downloaded) throw Error('Navigation download exceeds 40 MiB cap');
  if (!response.body) return response;
  const reader = response.body.getReader();
  const stream = new ReadableStream({
    async pull(controller) {
      const result = await reader.read();
      if (result.done) { controller.close(); return; }
      downloaded += result.value.byteLength;
      if (downloaded > cap) {
        await reader.cancel();
        controller.error(Error('Navigation download exceeds 40 MiB cap'));
        return;
      }
      controller.enqueue(result.value);
    },
    cancel(reason) { return reader.cancel(reason); }
  });
  return new Response(stream, {status: response.status, statusText: response.statusText, headers: response.headers});
};
let revision = null;
try {
  const response = await globalThis.fetch('https://huggingface.co/api/models/Xenova/all-MiniLM-L6-v2');
  if (response.ok) revision = (await response.json()).sha;
} catch { /* A cached model can still be benchmarked when revision lookup fails. */ }
const started = performance.now();
const {createEmbeddingReward} = await import('./build/reward.js');
const score = await createEmbeddingReward();
const startupMs = performance.now() - started;
const texts = ['contact us', 'account login', 'subscribe', 'book an appointment', 'privacy policy'];
const latencies = [];
const scores = [];
for (const text of texts) {
  const begin = performance.now();
  scores.push(await score({action: ['click'], origin: {text}}));
  latencies.push(performance.now() - begin);
}
const files = [];
function walk(dir) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
    const filename = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(filename);
    else if (entry.isFile()) {
      const bytes = fs.readFileSync(filename);
      files.push({path: path.relative(process.env.WEBFORM_MODEL_CACHE, filename), bytes: bytes.length, sha256: crypto.createHash('sha256').update(bytes).digest('hex')});
    }
  }
}
walk(process.env.WEBFORM_MODEL_CACHE);
if (!files.some(f => f.path.endsWith('model_quantized.onnx'))) throw Error('Quantized navigation model missing');
const result = {model: 'Xenova/all-MiniLM-L6-v2', requested_revision: 'main', observed_remote_revision: revision,
  quantized: true, cpu: os.cpus()[0]?.model, architecture: os.arch(), node: process.version,
  startup_ms: startupMs, short_link_ms: latencies, scores, texts, downloaded_bytes: downloaded,
  cache_bytes: files.reduce((sum, file) => sum + file.bytes, 0), files,
  mean_short_link_ms: latencies.reduce((a,b) => a+b,0) / latencies.length};
const previous = fs.existsSync(process.env.WEBFORM_WARM_REPORT)
  ? JSON.parse(fs.readFileSync(process.env.WEBFORM_WARM_REPORT, 'utf8')) : null;
result.first_measurement = previous?.first_measurement ?? (previous
  ? {startup_ms: previous.startup_ms, mean_short_link_ms: previous.mean_short_link_ms, downloaded_bytes: previous.downloaded_bytes}
  : {startup_ms: result.startup_ms, mean_short_link_ms: result.mean_short_link_ms, downloaded_bytes: result.downloaded_bytes});
fs.writeFileSync(process.env.WEBFORM_WARM_REPORT, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({startup_ms: startupMs, mean_short_link_ms: result.mean_short_link_ms,
  cache_bytes: result.cache_bytes, architecture: result.architecture}));
'''
    env = dict(os.environ, WEBFORM_MODEL_CACHE=str(cache), WEBFORM_WARM_REPORT=str(report))
    try:
        subprocess.run(['node', '--input-type=module', '-e', script], cwd=UPSTREAM / 'crawler', env=env, check=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise ValueError('Navigation warm check exceeded its 180-second timeout') from None
    except subprocess.CalledProcessError as error:
        raise ValueError(f'Navigation warm check failed with exit code {error.returncode}') from None


def download(args):
    """Accept only a named historical database, bounded compressed and expanded bytes."""
    import zstandard
    started = time.monotonic()
    if urlsplit(args.url).scheme != 'https':
        raise ValueError('Use the HTTPS artifact URL obtained through the access form.')
    DATA.mkdir(exist_ok=True)
    archive = DATA / (args.name + '.zst')
    database = DATA / args.name
    cap = int(args.max_compressed_gib * GIB)
    expanded_cap = int(args.max_expanded_gib * GIB)
    if database.exists():
        raise ValueError(f'{database} already exists. Use inspect/select; downloads never overwrite references.')
    free = shutil.disk_usage(DATA).free
    if free < cap + expanded_cap + RESERVE_BYTES:
        raise ValueError(f'Need {cap+expanded_cap+RESERVE_BYTES} bytes free for both caps and crawl reserve; have {free}. Choose caps after checking the advertised sizes.')
    request = urllib.request.Request(args.url, method='HEAD')
    with urllib.request.urlopen(request, timeout=30) as response:
        advertised = int(response.headers['Content-Length']) if response.headers.get('Content-Length') else None
    if advertised is not None and advertised > cap:
        raise ValueError(f'Advertised archive size {advertised} exceeds cap {cap}')
    part = archive.with_suffix('.zst.part')
    if archive.exists():
        raise ValueError(f'{archive} already exists. Remove an incomplete archive explicitly before retrying.')
    try:
        with urllib.request.urlopen(args.url, timeout=30) as response, part.open('wb') as out:
            total = 0
            while block := response.read(1024 ** 2):
                total += len(block)
                if total > cap:
                    raise ValueError('Compressed download exceeds cap')
                out.write(block)
        if advertised is not None and total != advertised:
            raise ValueError('Downloaded size differs from advertised Content-Length')
        digest = sha256(part)
        if args.sha256 and digest != args.sha256.lower():
            raise ValueError('Archive checksum differs from the supplied checksum')
        expanded = database.with_suffix('.db.part')
        try:
            with part.open('rb') as raw, zstandard.ZstdDecompressor().stream_reader(raw) as reader, expanded.open('wb') as out:
                expanded_bytes = 0
                while block := reader.read(1024 ** 2):
                    expanded_bytes += len(block)
                    if expanded_bytes > expanded_cap:
                        raise ValueError('Expanded database exceeds cap')
                    out.write(block)
            with connect(expanded) as con:
                if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('SQLite quick_check failed')
            expanded.rename(database)
            database.chmod(0o444)
            part.rename(archive)
        finally:
            expanded.unlink(missing_ok=True)
        record = {'name': args.name, 'advertised_bytes': advertised, 'compressed_bytes': total,
                  'expanded_bytes': expanded_bytes, 'archive_sha256': digest, 'database_sha256': sha256(database),
                  'publisher_checksum_verified': bool(args.sha256), 'elapsed_seconds': round(time.monotonic()-started, 3)}
        (DATA / (args.name + '.download.json')).write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record, indent=2))
    finally:
        part.unlink(missing_ok=True)


def decompress(args):
    """Expand an existing archive without changing it or overwriting a reference."""
    import zstandard
    started = time.monotonic()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    archive = Path(args.archive or output / (args.name + '.zst')).resolve(strict=True)
    database = output / args.name
    report = output / (args.name + '.decompress.json')
    cap = int(args.max_compressed_gib * GIB)
    expanded_cap = int(args.max_expanded_gib * GIB)
    compressed_bytes = archive.stat().st_size
    if compressed_bytes > cap:
        raise ValueError(f'Archive size {compressed_bytes} exceeds cap {cap}')
    digest = sha256(archive)
    if args.sha256 and digest != args.sha256.lower():
        raise ValueError('Archive checksum differs from the supplied checksum')
    if database.exists():
        if not report.exists():
            raise ValueError('Existing database has no decompression report; inspect it separately.')
        previous = json.loads(report.read_text())
        if (previous['archive_sha256'] != digest or previous['compressed_bytes'] != compressed_bytes
                or previous['expanded_bytes'] != database.stat().st_size
                or previous['database_sha256'] != sha256(database)):
            raise ValueError('Existing database/archive differs from its decompression report')
        if database.stat().st_size > expanded_cap:
            raise ValueError('Existing database exceeds expanded cap')
        with connect(database) as con:
            if [row[0] for row in con.execute('PRAGMA quick_check')] != ['ok']:
                raise ValueError('SQLite quick_check failed')
        database.chmod(0o444)
        print(f'Reused {database}, {database.stat().st_size} bytes')
        return previous
    free = shutil.disk_usage(output).free
    if free < expanded_cap + RESERVE_BYTES:
        raise ValueError(f'Need {expanded_cap + RESERVE_BYTES} bytes free for expansion cap and crawl reserve; have {free}')
    expanded = database.with_suffix('.db.part')
    if expanded.exists():
        raise ValueError(f'{expanded} already exists; preserve or remove the interrupted temporary file explicitly')
    try:
        with archive.open('rb') as raw, zstandard.ZstdDecompressor().stream_reader(raw) as reader, expanded.open('xb') as out:
            expanded_bytes = 0
            while block := reader.read(1024 ** 2):
                expanded_bytes += len(block)
                if expanded_bytes > expanded_cap:
                    raise ValueError('Expanded database exceeds cap')
                if shutil.disk_usage(output).free < RESERVE_BYTES + len(block):
                    raise ValueError('Free space reached the crawl reserve during decompression')
                out.write(block)
        with connect(expanded) as con:
            if [row[0] for row in con.execute('PRAGMA quick_check')] != ['ok']:
                raise ValueError('SQLite quick_check failed')
        database_digest = sha256(expanded)
        record = {'name': args.name, 'archive_path': str(archive), 'compressed_bytes': compressed_bytes,
                  'expanded_bytes': expanded_bytes, 'archive_sha256': digest,
                  'database_sha256': database_digest, 'sqlite_quick_check': 'ok',
                  'publisher_checksum_verified': False, 'supplied_checksum_verified': bool(args.sha256),
                  'max_compressed_bytes': cap, 'max_expanded_bytes': expanded_cap,
                  'crawl_reserve_bytes': RESERVE_BYTES,
                  'elapsed_seconds': round(time.monotonic() - started, 3)}
        expanded.chmod(0o444)
        expanded.rename(database)
        report.write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record, indent=2))
        return record
    except zstandard.ZstdError as e:
        raise ValueError(f'Invalid Zstandard archive: {e}') from e
    finally:
        expanded.unlink(missing_ok=True)


def self_test():
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        d, a = root / 'domain.db', root / 'webform-data.db'
        with sqlite3.connect(d) as con:
            con.executescript('CREATE TABLE tranco_list(ranking INTEGER PRIMARY KEY, domain TEXT UNIQUE); CREATE TABLE domain_info(domain TEXT UNIQUE, content_categories TEXT); CREATE TABLE http_info(domain TEXT UNIQUE, url TEXT);')
            for i in reversed(range(510)):
                domain = f'site{i:03}.example'
                con.execute('INSERT INTO tranco_list VALUES (?,?)', (i+1, domain))
                categories = '[]' if i == 0 else json.dumps([{'id': 1, 'name': 'Shopping', 'super_category_id': 2}])
                if i == 509:
                    categories = json.dumps([{'id': 2, 'name': 'Shopping & Auctions'}])
                con.execute('INSERT INTO domain_info VALUES (?,?)', (domain, categories))
                con.execute('INSERT INTO http_info VALUES (?,?)', (domain, 'https://' + domain))
        with sqlite3.connect(a) as con:
            con.executescript('CREATE TABLE form_classification(domain TEXT,job_hash TEXT,form_filename TEXT,form_type TEXT); CREATE TABLE field_classification(domain TEXT,job_hash TEXT,form_filename TEXT,field_list TEXT);')
            for i in range(510):
                domain = f'site{i:03}.example'
                con.execute('INSERT INTO form_classification VALUES (?,?,?,?)', (domain, str(i), 'form.json', 'Contact Form'))
                con.execute('INSERT INTO field_classification VALUES (?,?,?,?)', (domain, str(i), 'form.json', '["EmailAddress"]'))
            con.execute('UPDATE field_classification SET field_list=? WHERE domain=?', ('invalid json', 'site509.example'))
            con.execute('UPDATE field_classification SET job_hash=? WHERE domain=?', ('unjoined', 'site508.example'))
            con.execute('UPDATE field_classification SET field_list=? WHERE domain=?', ('["nonsense"]', 'site507.example'))
        original = {p: sha256(p) for p in [d, a]}
        args = argparse.Namespace(domain_db=d, annotation_db=a, output=root / 'out', count=COUNT, seed=SEED)
        select(args)
        select(args)
        rows = list(csv.DictReader((args.output / 'sites.csv').open()))
        expected = sorted(random.Random(SEED).sample([f'site{i:03}.example' for i in range(507)], COUNT))
        assert [r['domain'] for r in rows] == expected
        assert len(set(expected)) == COUNT
        manifest = json.loads((args.output / 'manifest.json').read_text())
        assert manifest['category_names']['2'] == 'Shopping & Auctions'
        assert all(sha256(p) == digest for p, digest in original.items())
        with connect(d) as con:
            try:
                con.execute('DELETE FROM tranco_list')
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError('Historical database accepted a write')
        args.count = 508
        try:
            select(args)
        except ValueError as e:
            assert 'Only 507 eligible' in str(e)
        else:
            raise AssertionError('Insufficient cohort accepted')
    import zstandard
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = root / 'fixture.db'
        with sqlite3.connect(original) as con:
            con.execute('CREATE TABLE fixture(value TEXT)')
            con.execute("INSERT INTO fixture VALUES ('historical')")
        archive = root / 'domain.db.zst'
        archive.write_bytes(zstandard.ZstdCompressor().compress(original.read_bytes()))
        archive_digest = sha256(archive)
        args = argparse.Namespace(name='domain.db', archive=archive, output=root, sha256=archive_digest,
                                  max_compressed_gib=1, max_expanded_gib=1 / GIB)
        try:
            decompress(args)
        except ValueError as e:
            assert 'exceeds cap' in str(e)
        else:
            raise AssertionError('Expanded cap was not enforced')
        assert not (root / 'domain.db').exists() and not (root / 'domain.db.part').exists()
        assert sha256(archive) == archive_digest
        args.max_expanded_gib = 1
        record = decompress(args)
        assert record['database_sha256'] == sha256(original)
        assert (root / 'domain.db').stat().st_mode & 0o222 == 0
        decompress(args)
        assert sha256(archive) == archive_digest
        args.sha256 = '0' * 64
        try:
            decompress(args)
        except ValueError as e:
            assert 'checksum differs' in str(e)
        else:
            raise AssertionError('Incorrect archive checksum accepted')
    print(f'Preparation self-test passed in {time.monotonic()-started:.3f} seconds')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    sub = parser.add_subparsers(dest='command')
    for name, fn in [('inspect', inspect), ('select', select)]:
        p = sub.add_parser(name)
        p.add_argument('--domain-db', type=Path, default=DATA / 'domain.db')
        p.add_argument('--annotation-db', type=Path, default=DATA / 'webform-data.db')
        p.set_defaults(fn=fn)
        if name == 'inspect':
            p.add_argument('--output', type=Path, default=DATA / 'schema.json')
        if name == 'select':
            p.add_argument('--count', type=int, default=COUNT)
            p.add_argument('--seed', type=int, default=SEED)
            p.add_argument('--output', type=Path, default=DATA)
    p = sub.add_parser('setup')
    p.add_argument('--skip-compile', action='store_true')
    p.add_argument('--warm-navigation', action='store_true', help='Warm and benchmark one CPU navigation model process, at most 40 MiB download')
    p.set_defaults(fn=setup)
    p = sub.add_parser('decompress')
    p.add_argument('name', choices=['domain.db', 'webform-data.db'])
    p.add_argument('--archive', type=Path, help='Defaults to data/<name>.zst')
    p.add_argument('--output', type=Path, default=DATA)
    p.add_argument('--sha256')
    p.add_argument('--max-compressed-gib', type=float, default=8)
    p.add_argument('--max-expanded-gib', type=float, default=24)
    p.set_defaults(fn=decompress)
    p = sub.add_parser('download')
    p.add_argument('name', choices=['domain.db', 'webform-data.db'])
    p.add_argument('--url', required=True)
    p.add_argument('--sha256')
    p.add_argument('--max-compressed-gib', type=float, default=8)
    p.add_argument('--max-expanded-gib', type=float, default=24)
    p.set_defaults(fn=download)
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        elif args.command:
            if getattr(args, 'count', 1) <= 0 or getattr(args, 'max_compressed_gib', 1) <= 0 or getattr(args, 'max_expanded_gib', 1) <= 0:
                raise ValueError('Counts and byte caps must be positive')
            args.fn(args)
        else:
            parser.print_help()
    except (ValueError, OSError, sqlite3.Error, subprocess.CalledProcessError) as e:
        print(f'Preparation failed: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
