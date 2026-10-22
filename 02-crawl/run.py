#!/usr/bin/env python3
"""Run bounded site crawls and export form evidence for annotation."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import re
import sqlite3
from html.parser import HTMLParser
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / '02-crawl' / 'data'
CRAWLER = ROOT / 'upstream' / 'crawler'
SETTINGS = dict(workers=4, jobs=20, timeout=600, budget_gib=10,
                locale='en-US', timezone='Europe/Stockholm', latitude=59.3293,
                longitude=18.0686, egress_country='Sweden')
STATUS_FIELDS = ['domain', 'status', 'elapsed_seconds', 'bytes', 'jobs', 'pages', 'forms',
                 'attempt', 'started_at', 'returncode', 'peak_rss_bytes']


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:24]


def byte_count(path):
    total = 0
    for file in path.rglob('*') if path.exists() else []:
        try:
            metadata = file.stat()
        except FileNotFoundError:
            # Chromium and worker cleanup delete temporary files during scans.
            continue
        if stat.S_ISREG(metadata.st_mode):
            total += metadata.st_size
    return total


def recover_statuses(rows, domains):
    """Reuse worker records saved before an interrupted controller CSV update."""
    recovered = 0
    for path in sorted((DATA / 'captures').glob('*/*-status.json')):
        if path.parent.name not in domains:
            continue
        row = json.loads(path.read_text())
        if set(row) != set(STATUS_FIELDS) or row['domain'] != path.parent.name:
            raise ValueError('Invalid saved attempt-status record')
        attempt = int(row['attempt'])
        if path.name != f'attempt-{attempt:04d}-status.json':
            raise ValueError('Attempt-status identity mismatch')
        current = int(rows.get(row['domain'], {}).get('attempt') or 0)
        if attempt > current:
            rows[row['domain']] = row
            recovered += 1
    if recovered:
        write_status(rows)
        print(f'Recovered {recovered} saved site-status records after controller interruption')
    return recovered


def storage_self_test():
    from types import SimpleNamespace
    class DeletedFile:
        def stat(self):
            raise FileNotFoundError('Temporary browser file disappeared')
    class ScanRoot:
        def exists(self):
            return True
        def rglob(self, pattern):
            return iter([SimpleNamespace(stat=lambda: SimpleNamespace(st_mode=stat.S_IFREG, st_size=7)),
                         DeletedFile(), SimpleNamespace(stat=lambda: SimpleNamespace(st_mode=stat.S_IFDIR, st_size=50))])
    assert byte_count(ScanRoot()) == 7
    global DATA
    original_data = DATA
    with tempfile.TemporaryDirectory(prefix='webform-status-recovery-') as temp:
        try:
            DATA = Path(temp)
            folder = DATA / 'captures/example.test'
            folder.mkdir(parents=True)
            old = dict.fromkeys(STATUS_FIELDS, '')
            old.update(domain='example.test', attempt=1, status='partial_timeout')
            completed = dict(old, attempt=2, status='complete', pages=3, forms=2)
            (folder / 'attempt-0001-status.json').write_text(json.dumps(old))
            (folder / 'attempt-0002-status.json').write_text(json.dumps(completed))
            rows = {'example.test': old}
            assert recover_statuses(rows, {'example.test'}) == 1
            assert rows['example.test'] == completed
            assert recover_statuses(rows, {'example.test'}) == 0
            assert next(csv.DictReader((DATA / 'statuses.csv').open()))['status'] == 'complete'
        finally:
            DATA = original_data
    print('Temporary-file deletion and saved site-status recovery fixtures passed')


def normalize(domain, job_hash, filename, form, job):
    form_id = identity(domain, job_hash, filename)
    grouped = {}
    for index, field in enumerate(form.get('fields', [])):
        element = field['fieldElement']
        if element.get('tagName') not in {'INPUT', 'SELECT', 'TEXTAREA'}:
            continue
        attrs = element.get('attributes', {})
        name = field.get('name') or ''
        group_key = name or f'unnamed:{index}'
        group_id = identity(form_id, group_key)
        group = grouped.setdefault(group_key, dict(group_id=group_id, controls=[]))
        label = (field.get('labelElement', {}).get('text') or attrs.get('aria-label')
                 or field.get('previousElement', {}).get('text') or attrs.get('placeholder') or '')
        if field.get('groupLabel'):
            label = field['groupLabel'] + ': ' + label
        group['controls'].append(dict(
            field_id=identity(form_id, group_key, index), name=name, label=label,
            type=attrs.get('type', 'text' if element.get('tagName') == 'INPUT' else element.get('tagName', '').lower()),
            attributes={key: attrs[key] for key in ['placeholder', 'aria-label', 'aria-description', 'title',
                        'autocomplete', 'inputmode', 'pattern', 'min', 'max', 'step'] if key in attrs},
            options=field.get('options', []),
            visible=bool(element.get('isVisible')), disabled=field.get('disabled', 'disabled' in attrs),
            read_only=field.get('readOnly', 'readonly' in attrs),
            html_required=field.get('htmlRequired', 'required' in attrs),
            aria_required=field.get('ariaRequired', attrs.get('aria-required')),
            required_text=field.get('requiredText', []), optional_text=field.get('optionalText', [])))
    return dict(domain=domain, job_hash=job_hash, form_filename=filename, form_id=form_id,
                page_title=job.get('pageTitle', ''),
                buttons=[b.get('text') or b.get('attributes', {}).get('aria-label') or b.get('attributes', {}).get('title') or ''
                         for b in form.get('buttons', []) if b.get('isVisible')
                         and 'disabled' not in b.get('attributes', {})], groups=list(grouped.values()))


def export(captures, output):
    records = {}
    skipped = []
    status_path = captures.parent / 'statuses.csv'
    statuses = {r['domain']: r for r in csv.DictReader(status_path.open())} if status_path.exists() else {}
    chosen = {}
    for domain_dir in captures.iterdir() if captures.exists() else []:
        if domain_dir.name in statuses and statuses[domain_dir.name].get('attempt'):
            chosen[domain_dir.name] = f"attempt-{int(statuses[domain_dir.name]['attempt']):04d}"
        else:
            attempts = sorted(domain_dir.glob('attempt-*'))
            attempts = [p for p in attempts if p.is_dir()]
            if attempts:
                chosen[domain_dir.name] = attempts[-1].name
    for path in sorted(captures.glob('*/*/*/form-*.json')):
        if chosen.get(path.relative_to(captures).parts[0]) != path.relative_to(captures).parts[1]:
            continue
        domain, attempt, job_hash = path.relative_to(captures).parts[:3]
        job_path = path.parent / 'job.json'
        if not job_path.exists():
            continue
        try:
            row = normalize(domain, job_hash, path.name, json.loads(path.read_text()),
                            json.loads(job_path.read_text()))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            skipped.append(dict(path=str(path.relative_to(captures)), error=type(exc).__name__))
            continue
        records[row['form_id']] = row
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    with temporary.open('w') as f:
        for key in sorted(records):
            f.write(json.dumps(records[key], ensure_ascii=False) + '\n')
    temporary.replace(output)
    output.with_name('export-summary.json').write_text(json.dumps(dict(forms=len(records),
            skipped_incomplete_or_invalid=len(skipped), skipped=skipped), indent=2))
    return len(records)


CONTEXT_VERSION = 'saved-dom-context-v3.1'


class ContextDOM(HTMLParser):
    """Minimal saved-HTML tree; never executes scripts or opens a browser."""
    VOID = {'input', 'br', 'img', 'hr', 'meta', 'link', 'area', 'base', 'embed', 'source', 'wbr'}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = {'tag': 'root', 'attrs': {}, 'children': [], 'parent': None}
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'attrs': dict(attrs), 'children': [], 'parent': self.stack[-1]}
        self.stack[-1]['children'].append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]['tag'] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1]['children'].append(data)


def dom_nodes(node):
    yield node
    for child in node['children']:
        if isinstance(child, dict):
            yield from dom_nodes(child)


def safe_node_text(node):
    attrs = node['attrs']
    if (node['tag'] in {'script', 'style', 'template', 'noscript', 'input', 'select', 'textarea', 'option'}
            or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
            or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style') or '', re.I)):
        return ''
    return ' '.join(safe_node_text(c) if isinstance(c, dict) else c for c in node['children'])


def context_secrets(raw, dom):
    secrets = set()
    def values(value):
        if isinstance(value, dict):
            for item in value.values():
                values(item)
        elif isinstance(value, list):
            for item in value:
                values(item)
        elif value is not None and str(value).strip():
            secrets.add(' '.join(str(value).split()))
    values(raw.get('defaultFormData', {}))
    for node in dom_nodes(dom):
        if node['tag'] in {'input', 'option', 'button'}:
            values(node['attrs'].get('value'))
        if node['tag'] == 'textarea':
            values(' '.join(c for c in node['children'] if isinstance(c, str)))
    return secrets


def sanitize_context(text, secrets=()):
    text = ' '.join(str(text or '').split())
    for value in sorted(secrets, key=len, reverse=True):
        text = re.sub(r'(?<!\w)' + re.escape(value) + r'(?!\w)', '[removed value]', text, flags=re.I)
    text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[removed email]', text)
    text = re.sub(r'[a-z][a-z0-9+.-]*://\S+|www\.\S+|(?:/[^\s?]*)?\?[^\s]+', '[removed URL]', text, flags=re.I)
    text = re.sub(r'(?<![\w@])(?:[\w-]+\.)+(?:[a-z]{2,}|xn--[\w-]+)(?::\d+)?(?:/[^\s]*)?', '[removed URL]', text, flags=re.I)
    text = re.sub(r'(?<!\w)/[^\s]+', '[removed URL]', text)
    text = re.sub(r'\b(?:token|secret|csrf|nonce|session|authorization|api[_-]?key)\s*[=:]\s*[^\s]+|\bBearer\s+\S+', '[removed token]', text, flags=re.I)
    text = re.sub(r'\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b|[A-Za-z0-9_+/=-]{24,}', '[removed opaque text]', text, flags=re.I)
    text = re.sub(r'\b[A-Za-z_][\w.-]*=[^\s&]+(?:&[^\s]+)*', '[removed parameter]', text)
    return ' '.join(text.split())[:240]


def saved_context(raw, page_html):
    form_dom = ContextDOM(raw.get('element', {}).get('outerHTML', '')).root
    page_dom = ContextDOM(page_html).root
    secrets = context_secrets(raw, page_dom) | context_secrets(raw, form_dom)
    candidates = [(n, 'inside_saved_form') for n in dom_nodes(form_dom)
                  if n['tag'] in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'legend', 'p'}]
    form_nodes = [n for n in dom_nodes(form_dom) if n['tag'] == 'form']
    # Only an unambiguous HTML form id allows adding outside context. Synthetic
    # forms and unidentifiable forms retain local subtree evidence only.
    form_id = form_nodes[0]['attrs'].get('id') if len(form_nodes) == 1 else None
    matches = [n for n in dom_nodes(page_dom) if n['tag'] == 'form' and n['attrs'].get('id') == form_id] if form_id else []
    if len(matches) == 1:
        target = matches[0]
        siblings = [n for n in target['parent']['children'] if isinstance(n, dict)]
        position = next(i for i, n in enumerate(siblings) if n is target)
        for sibling in siblings[max(0, position - 2):position]:
            if sibling['tag'] in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'}:
                candidates.insert(0, (sibling, 'preceding_same_parent_form_id'))
    headings, descriptions, associations, seen = [], [], [], set()
    for node, association in candidates:
        ancestor = node['parent']
        excluded = False
        while ancestor:
            attrs = ancestor['attrs']
            if (ancestor['tag'] in {'script', 'style', 'template', 'noscript'} or 'hidden' in attrs
                    or attrs.get('aria-hidden') == 'true' or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style') or '', re.I)):
                excluded = True
                break
            ancestor = ancestor['parent']
        if excluded:
            continue
        text = sanitize_context(safe_node_text(node), secrets)
        if not text or text in seen:
            continue
        output = descriptions if node['tag'] == 'p' else headings
        if len(output) >= (4 if node['tag'] == 'p' else 4):
            continue
        if sum(len(t) for t in headings + descriptions) + len(text) > 1200:
            continue
        output.append(text)
        associations.append({'kind': 'description' if node['tag'] == 'p' else 'heading', 'association': association})
        seen.add(text)
    return {'version': CONTEXT_VERSION, 'headings': headings, 'descriptions': descriptions,
            'associations': associations}


def default_context_selection():
    complete = {r['domain'] for r in csv.DictReader((DATA / 'statuses.csv').open()) if r['status'] == 'complete'}
    identifying = {'Address', 'EmailAddress', 'GovernmentId', 'BankAccountNumber', 'PersonName',
                   'PhoneNumber', 'UsernameOrOtherId', 'TaxId'}
    # Join by capture identity via the immutable export; annotation_state lacks job columns.
    forms = {f['form_id']: f for f in (json.loads(line) for line in (DATA / 'forms.jsonl').open())}
    connection = sqlite3.connect((ROOT / '05-analyze/data/results.db').resolve().as_uri() + '?mode=ro', uri=True)
    rows = {(d, j, n): (purpose, fields) for d, j, n, purpose, fields in connection.execute(
        'SELECT domain,job_hash,form_filename,form_type,field_list FROM form_classification JOIN field_classification USING(domain,job_hash,form_filename)')}
    connection.close()
    return {fid for fid, f in forms.items() if f['domain'] in complete and
            ((row := rows[(f['domain'], f['job_hash'], f['form_filename'])])[1] is None or
             (row[0] == 'Unknown' and not identifying.isdisjoint(json.loads(row[1]))))}


def export_context(selection_path=None):
    output_dir = DATA / 'methodology-v3'
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = default_context_selection() if selection_path is None else set(json.loads(selection_path.read_text())['form_ids'])
    statuses = {r['domain']: r for r in csv.DictReader((DATA / 'statuses.csv').open())}
    baseline = DATA / 'forms.jsonl'
    records, examples, enriched = [], [], 0
    for line in baseline.open():
        row = json.loads(line)
        if row['form_id'] in selected:
            path = DATA / 'captures' / row['domain'] / f"attempt-{int(statuses[row['domain']]['attempt']):04d}" / row['job_hash'] / row['form_filename']
            page_path = path.with_name('page.html')
            raw = json.loads(path.read_text())
            context = saved_context(raw, page_path.read_text())
            row['local_context'] = context
            row['context_source'] = {'capture_path': str(path.relative_to(DATA)),
                'form_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'page_sha256': hashlib.sha256(page_path.read_bytes()).hexdigest(),
                'baseline_record_sha256': hashlib.sha256(line.encode()).hexdigest(),
                'selection_reason': 'baseline_comparison_blocker' if selection_path is None else 'explicit_selected_form'}
            if context['headings'] or context['descriptions']:
                enriched += 1
                if len(examples) < 12:
                    examples.append({'domain': row['domain'], 'form_id': row['form_id'], 'local_context': context})
        records.append(row)
    assert selected <= {r['form_id'] for r in records}, 'Selection contains unknown form identities'
    (output_dir / 'forms.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records))
    report = {'version': CONTEXT_VERSION, 'forms': len(records), 'selected_forms': len(selected),
        'forms_with_added_text': enriched, 'baseline_forms_sha256': hashlib.sha256(baseline.read_bytes()).hexdigest(),
        'selection_form_ids': sorted(selected), 'examples': examples,
        'limits': {'text_chars': 240, 'heading_count': 4, 'description_count': 4, 'total_text_chars': 1200},
        'limitations': 'Saved inline hidden flags only; external CSS visibility unavailable. Context is inside saved form or direct preceding heading/paragraph with unique matching form id. No whole-form inner text.'}
    (output_dir / 'context-export-summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Saved {len(records)} forms; enriched {enriched} of {len(selected)} selected forms")
    return report


def context_self_test():
    raw = {'element': {'outerHTML': '<form id="n"><h2>Newsletter</h2><p>Receive updates. hello@example.org https://bad.test/?token=secret SecretValue csrf=secret123 ABCDEFGHIJKLMNOPQRSTUVWXYZ012345</p><input value="SecretValue"><select><option value="secret-option">Selected private value</option></select><textarea>private prose</textarea><p hidden>Hidden prose</p></form>'},
           'defaultFormData': {'x': 'SecretValue'}}
    context = saved_context(raw, '<section><h2>Subscribe today</h2>' + raw['element']['outerHTML'] + '</section>')
    text = json.dumps(context)
    for forbidden in ['hello@example.org', 'https://', 'SecretValue', 'secret123', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ012345', 'Selected private value', 'private prose', 'Hidden prose']:
        assert forbidden not in text, forbidden
    assert context['headings'] == ['Subscribe today', 'Newsletter']
    assert 'Receive updates.' in context['descriptions'][0]
    assert not saved_context({'element': {'outerHTML': '<form><input></form>'}}, '<h2>Unassociated</h2><form><input></form>')['headings']
    hidden = {'element': {'outerHTML': '<form><div style="display:none"><h2>Hidden ancestor</h2></div><p>Private prose</p></form>'},
              'defaultFormData': {'x': 'Private\nprose'}}
    assert not saved_context(hidden, '')['headings']
    assert 'Private prose' not in json.dumps(saved_context(hidden, ''))
    for value in ['bare.test/path', '/private/route', 'session=abc123', 'Bearer abc123', '32b6a150-c842-498b-83d6-3264aee49b7a']:
        assert value not in sanitize_context(value)
    (DATA / 'methodology-v3').mkdir(parents=True, exist_ok=True)
    (DATA / 'methodology-v3/context-fixture-report.json').write_text(json.dumps({'passed': True,
        'checks': ['default_values', 'control_values', 'textarea', 'selected_options', 'emails', 'URLs', 'tokens', 'hidden_text', 'hidden_ancestor', 'multiline_values', 'DOM_association', 'unassociated_exclusion']}))
    print('Saved DOM context and sanitizer fixtures passed')


def counts(path):
    jobs = list(path.glob('*/job.json'))
    return dict(jobs=len([p for p in path.iterdir() if p.is_dir()]) if path.exists() else 0,
                pages=len(jobs), forms=len(list(path.glob('*/form-*.json'))))


def write_status(rows):
    temporary = DATA / 'statuses.tmp'
    with temporary.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=STATUS_FIELDS)
        writer.writeheader()
        writer.writerows(rows.values())
    temporary.replace(DATA / 'statuses.csv')


def stop_process(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    except ProcessLookupError:
        pass


def resident_bytes(pid):
    result = subprocess.run(['ps', '-axo', 'pid=,ppid=,rss='], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    processes = [tuple(map(int, line.split())) for line in result.stdout.splitlines() if len(line.split()) == 3]
    descendants = {pid}
    while True:
        found = {child for child, parent, rss in processes if parent in descendants}
        if found.issubset(descendants):
            break
        descendants.update(found)
    return sum(rss * 1024 for child, parent, rss in processes if child in descendants)


def run_site(site, args, stop):
    domain = site['domain']
    directory = DATA / 'captures' / domain
    attempt = max([int(p.name.split('-')[1]) for p in directory.glob('attempt-*') if p.is_dir()] or [0]) + 1
    out = directory / f'attempt-{attempt:04d}'
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = DATA / 'browser-cache' / identity(threading.current_thread().name)
    cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if (ROOT / '.browsers').exists():
        env.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT / '.browsers'))
    env['XDG_CACHE_HOME'] = str(cache)
    env['WEBFORM_MODEL_CACHE'] = str(DATA / 'navigation-model-cache')
    cmd = [args.node, str(CRAWLER / 'build' / 'crawler.js'), str(out), site['start_url'],
           '--maxJobCount', str(args.jobs), '--minJobTime', '0', '--screenshots=false',
           '--locale', SETTINGS['locale'], '--timezone', args.timezone,
           '--latitude', str(args.latitude), '--longitude', str(args.longitude)]
    started = time.monotonic()
    row = dict(domain=domain, started_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               attempt=attempt, peak_rss_bytes=0, status='failed', returncode='')
    process = None
    try:
        with (directory / f'attempt-{attempt:04d}.log').open('w') as log:
            process = subprocess.Popen(cmd, cwd=CRAWLER, env=env, stdout=log, stderr=log,
                                       start_new_session=True)
            while process.poll() is None:
                rss = resident_bytes(process.pid)
                if rss is not None:
                    row['peak_rss_bytes'] = max(row['peak_rss_bytes'] or 0, rss)
                else:
                    row['peak_rss_bytes'] = ''
                if stop.is_set():
                    row['status'] = stop.reason
                    stop_process(process)
                    break
                if time.monotonic() - started >= args.timeout:
                    row['status'] = 'partial_timeout'
                    stop_process(process)
                    break
                time.sleep(0.25)
            row['returncode'] = process.returncode
            if row['status'] == 'failed' and process.returncode == 0:
                row['status'] = 'complete' if counts(out)['pages'] else 'unreached'
    except Exception as exc:
        row['status'] = 'failed'
        print(f"{domain}: process error {type(exc).__name__}")
    finally:
        if process is not None and process.poll() is None:
            stop_process(process)
        if process is not None:
            row['returncode'] = process.returncode
            import shutil
            shutil.rmtree(cache / 'web-form-crawler' / f'user-data-{process.pid}', ignore_errors=True)
    row.update(counts(out), elapsed_seconds=round(time.monotonic() - started, 3), bytes=byte_count(directory))
    (directory / f'attempt-{attempt:04d}-status.json').write_text(json.dumps(row, indent=2))
    return row


def self_test(node):
    storage_self_test()
    global DATA
    import sys
    from types import SimpleNamespace
    fixture_started = time.monotonic()
    form = dict(fields=[dict(name='choice', fieldElement=dict(tagName='INPUT', isVisible=True,
                attributes={'type': 'radio', 'required': '', 'value': 'secret'})),
                dict(name='choice', fieldElement=dict(tagName='INPUT', isVisible=False, attributes={'type': 'radio'}))],
                buttons=[dict(text='Register', isVisible=True, attributes={}),
                         dict(text='HIDDEN-BUTTON', isVisible=False, attributes={}),
                         dict(text='DISABLED-BUTTON', isVisible=True, attributes={'disabled': ''})])
    record = normalize('example.test', 'job', 'form-0.json', form, {'pageTitle': 'Fixture'})
    assert len(record['groups']) == 1 and len(record['groups'][0]['controls']) == 2
    assert record['groups'][0]['controls'][0]['html_required'] is True
    assert 'secret' not in json.dumps(record) and 'defaultFormData' not in json.dumps(record)
    assert record['buttons'] == ['Register']
    assert normalize('example.test', 'job', 'form-0.json', form, {})['form_id'] == record['form_id']
    code = r'''
import { chromium } from 'playwright';
import { getFormInformation } from './build/page-functions.js';
import { checkForms, saveJobInformation } from './build/crawler.js';
import fs from 'node:fs/promises';
const browser = await chromium.launch();
try {
const page = await browser.newPage();
await page.setContent(`<form><label for="email">Email required</label><input id="email" name="email" required="" aria-required="false"><input name="token" type="hidden" value="secret"><label><input name="news" type="checkbox" disabled>News optional</label><fieldset><legend>Choice</legend><label><input name="choice" type="radio">Yes</label><label><input name="choice" type="radio">No</label></fieldset><label for="country">Country not required</label><select id="country" name="country"><option value="secret-code">Sweden</option><option value="secret-code2">Finland</option></select><button>Register</button></form>`);
const info = await page.locator('form').evaluate(getFormInformation);
if (!info.fields[0].htmlRequired || info.fields[0].ariaRequired !== 'false' || info.fields[1].fieldElement.isVisible || !info.fields[2].disabled || info.fields[2].optionalText.length !== 1) throw Error('Extraction evidence failed');
if (info.fields.some(x => x.fieldElement.tagName === 'FIELDSET') || info.fields[5].options.join(',') !== 'Sweden,Finland' || info.fields[5].requiredText.length || !info.fields[5].optionalText.includes('not required')) throw Error('Select or negated requiredness failed');
const dir = process.env.WEBFORM_FIXTURE_DIR;
await saveJobInformation(page, dir, {priority:1,parents:[],steps:[]}, [], false);
await checkForms(page, dir, false);
const files = await fs.readdir(dir);
if (!files.includes('job.json') || !files.includes('form-0.json') || !files.includes('page.html') || files.some(x => x.endsWith('.png'))) throw Error('Screenshot-disabled capture failed');
console.log('Playwright visibility, requiredness, radio group and screenshot-disabled metadata checks passed');
} finally { await browser.close(); }
'''
    with tempfile.TemporaryDirectory(prefix='webform-export-fixture-') as temp:
        base = Path(temp)
        for attempt, title in [(1, 'stale'), (2, 'current')]:
            folder = base / 'captures' / 'example.test' / f'attempt-{attempt:04d}' / 'job'
            folder.mkdir(parents=True)
            (folder / 'job.json').write_text(json.dumps({'pageTitle': title}))
            (folder / 'form-0.json').write_text(json.dumps(form))
        (base / 'statuses.csv').write_text('domain,attempt\nexample.test,2\n')
        assert export(base / 'captures', base / 'forms.jsonl') == 1
        assert json.loads((base / 'forms.jsonl').read_text())['page_title'] == 'current'
        (folder / 'form-1.json').write_text('{')
        assert export(base / 'captures', base / 'forms.jsonl') == 1
        assert json.loads((base / 'export-summary.json').read_text())['skipped_incomplete_or_invalid'] == 1
    with tempfile.TemporaryDirectory(prefix='webform-process-fixture-') as temp:
        original_data = DATA
        DATA = Path(temp)
        fake = DATA / 'fake-node'
        fake.write_text('#!' + sys.executable + '\n' +
            "import pathlib,sys,json,time\n" +
            "job=pathlib.Path(sys.argv[2])/'job';job.mkdir(parents=True)\n" +
            "(job/'job.json').write_text(json.dumps({'pageTitle':'Partial'}))\n" +
            "(job/'form-0.json').write_text(" + repr(json.dumps(form)) + ")\n" +
            "time.sleep(30)\n")
        fake.chmod(0o755)
        stop = threading.Event()
        stop.reason = 'storage_limit'
        args = SimpleNamespace(node=str(fake), jobs=1, timezone=SETTINGS['timezone'],
                    latitude=SETTINGS['latitude'], longitude=SETTINGS['longitude'], timeout=0.3)
        try:
            row = run_site(dict(domain='example.test', start_url='https://example.test'), args, stop)
            assert row['status'] == 'partial_timeout' and row['forms'] == 1 and row['attempt'] == 1
            write_status({'example.test': row})
            assert export(DATA / 'captures', DATA / 'forms.jsonl') == 1
            stop.set()
            row2 = run_site(dict(domain='example.test', start_url='https://example.test'), args, stop)
            assert row2['status'] == 'storage_limit' and row2['attempt'] == 2
        finally:
            DATA = original_data
    with tempfile.TemporaryDirectory(prefix='webform-fixture-') as temp:
        subprocess.run([node, '--input-type=module', '-e', code], cwd=CRAWLER,
                       env={**os.environ, 'WEBFORM_FIXTURE_DIR': temp,
                            'PLAYWRIGHT_BROWSERS_PATH': os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(ROOT / '.browsers'))},
                       check=True, timeout=90)
    print('Normalization, latest-attempt export, malformed writes, timeout and storage-stop checks passed')
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'fixture-report.json').write_text(json.dumps(dict(passed=True, elapsed_seconds=round(time.monotonic() - fixture_started, 3),
        checks=['identity', 'radio_groups', 'no_raw_values', 'latest_attempt', 'incomplete_json', 'timeout',
                'storage_stop', 'visibility', 'requiredness', 'select_options', 'screenshots_disabled']), indent=2))


def main_inner():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sites', type=Path, default=ROOT / '01-prepare' / 'data' / 'sites.csv')
    parser.add_argument('--pilot', action='store_true', help='Use the first 10 fixed cohort domains')
    parser.add_argument('--full', action='store_true', help='Run the fixed cohort after reviewing the pilot forecast')
    parser.add_argument('--accept-pilot-forecast', action='store_true', help='Confirm reviewed pilot forecast before full run')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--context-export', action='store_true', help='Enrich selected saved forms in methodology-v3, without crawling')
    parser.add_argument('--context-selection', type=Path, help='JSON object with form_ids; defaults to baseline comparison blockers')
    parser.add_argument('--context-self-test', action='store_true', help='Offline DOM context and privacy fixtures')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--node', default='node')
    for key in ['workers', 'jobs', 'timeout']:
        parser.add_argument('--' + key, type=int, default=SETTINGS[key])
    for key in ['budget_gib', 'latitude', 'longitude']:
        parser.add_argument('--' + key.replace('_', '-'), type=float, default=SETTINGS[key])
    parser.add_argument('--timezone', default=SETTINGS['timezone'])
    parser.add_argument('--egress-country', default=SETTINGS['egress_country'])
    args = parser.parse_args()
    if args.context_self_test:
        context_self_test()
        return
    if args.context_export:
        export_context(args.context_selection)
        return
    if args.self_test:
        self_test(args.node)
        return
    DATA.mkdir(parents=True, exist_ok=True)
    if args.export:
        print(f"Exported {export(DATA / 'captures', DATA / 'forms.jsonl')} forms")
        return
    if args.full:
        pilot_path = DATA / 'pilot-summary.json'
        if not pilot_path.exists() or not args.accept_pilot_forecast:
            parser.error('Full run requires a saved pilot and --accept-pilot-forecast after review')
        pilot = json.loads(pilot_path.read_text())
        forecast = pilot.get('forecast_total_output_bytes_500')
        if not pilot.get('attempted') or forecast is None or forecast >= args.budget_gib * 1024**3:
            parser.error('Pilot storage forecast is missing or exceeds the output budget; reduce depth and rerun pilot')
    if args.pilot == args.full:
        parser.error('Choose exactly one of --pilot or --full')
    if args.budget_gib > 10:
        parser.error('The crawl-output ceiling is 10 GiB')
    if min(args.workers, args.jobs, args.timeout, args.budget_gib) <= 0:
        parser.error('Workers, jobs, timeout and budget must be positive')
    if not args.egress_country.strip():
        parser.error('European egress country is required')
    with args.sites.open(newline='') as f:
        sites = list(csv.DictReader(f))
    if len({s['domain'] for s in sites}) != len(sites):
        parser.error('Cohort domains must be unique')
    if any('/' in s['domain'] or s['domain'] in {'.', '..'} or not s['start_url'].startswith(('https://', 'http://')) for s in sites):
        parser.error('Invalid cohort domain or starting URL')
    cohort_checksum = hashlib.sha256(args.sites.read_bytes()).hexdigest()
    if args.full and pilot.get('cohort_checksum') != cohort_checksum:
        parser.error('Pilot belongs to a different cohort')
    if args.full and pilot.get('settings', {}).get('jobs') != args.jobs:
        parser.error('Full-run job cap must match the reviewed pilot')
    if args.pilot:
        sites = sites[:10]
    status_path = DATA / 'statuses.csv'
    rows = {r['domain']: r for r in csv.DictReader(status_path.open())} if status_path.exists() else {}
    recover_statuses(rows, {s['domain'] for s in sites})
    requested_sites = sites.copy()
    sites = [s for s in sites if rows.get(s['domain'], {}).get('status') != 'complete']
    if not sites:
        print('All requested sites are complete; existing summary retained.')
        return
    manifest = dict(settings={**SETTINGS, **vars(args)}, started_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    navigation='Original MiniLM-L6-v2 CPU scorer, shared cache', screenshots=False,
                    requiredness='Separate signals, absence is unspecified')
    (DATA / 'run-manifest.json').write_text(json.dumps(manifest, indent=2, default=str))
    stop = threading.Event()
    stop.reason = 'storage_limit'
    previous_handler = signal.getsignal(signal.SIGINT)
    def interrupt(signum, frame):
        stop.reason = 'partial_interrupted'
        stop.set()
    signal.signal(signal.SIGINT, interrupt)
    budget = int(args.budget_gib * 1024**3)
    # Leave 64 MiB per worker for writes already underway when the monitor stops processes.
    threshold = max(0, budget - args.workers * 64 * 1024**2)
    started = time.monotonic()
    pending = iter(sites)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        active = {}
        while True:
            if byte_count(DATA) >= threshold:
                stop.set()
            while len(active) < args.workers and not stop.is_set():
                site = next(pending, None)
                if site is None:
                    break
                active[pool.submit(run_site, site, args, stop)] = site
            if not active:
                break
            done, _ = concurrent.futures.wait(active, timeout=0.25,
                                              return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                site = active.pop(future)
                try:
                    row = future.result()
                except Exception as exc:
                    row = dict.fromkeys(STATUS_FIELDS, '')
                    row.update(domain=site['domain'], status='failed', forms=0, jobs=0, pages=0, bytes=0)
                    print(f"{site['domain']}: {type(exc).__name__}")
                rows[row['domain']] = row
                write_status(rows)
                print(f"{row['domain']}: {row['status']}, {row['forms']} forms")
    signal.signal(signal.SIGINT, previous_handler)
    forms = export(DATA / 'captures', DATA / 'forms.jsonl')
    elapsed = time.monotonic() - started
    selected_rows = [rows[s['domain']] for s in requested_sites if s['domain'] in rows]
    attempted = len(selected_rows)
    capture_bytes = sum(int(r['bytes'] or 0) for r in selected_rows)
    normalized_bytes = (DATA / 'forms.jsonl').stat().st_size
    fixed_bytes = max(0, byte_count(DATA) - byte_count(DATA / 'captures') - normalized_bytes)
    summary = dict(cohort_checksum=cohort_checksum, settings=dict(jobs=args.jobs, workers=args.workers, timeout=args.timeout),
                   elapsed_seconds=round(elapsed, 3), attempted=attempted, exported_forms=forms,
                   failures=sum(r['status'] != 'complete' for r in selected_rows), storage_stopped=stop.is_set() and stop.reason == 'storage_limit',
                   interrupted=stop.is_set() and stop.reason == 'partial_interrupted',
                   output_bytes=byte_count(DATA), budget_exceeded_bytes=max(0, byte_count(DATA) - budget), forecast_capture_bytes_500=capture_bytes / attempted * 500 if attempted else None,
                   forecast_total_output_bytes_500=fixed_bytes + (capture_bytes + normalized_bytes) / attempted * 500 if attempted else None,
                   forecast_seconds_500=sum(float(r['elapsed_seconds'] or 0) for r in selected_rows) / attempted * 500 / args.workers if attempted else None,
                   forecast_seconds_500_from_pilot_wall=elapsed / attempted * 500 if attempted else None,
                   measured_sites_per_hour=attempted / elapsed * 3600 if elapsed else None,
                   effective_parallel_site_processes=sum(float(r['elapsed_seconds'] or 0) for r in selected_rows) / elapsed if elapsed else None,
                   outcomes={status: sum(r['status'] == status for r in selected_rows) for status in sorted({r['status'] for r in selected_rows})},
                   saved_pages=sum(int(r['pages'] or 0) for r in selected_rows),
                   started_jobs=sum(int(r['jobs'] or 0) for r in selected_rows),
                   forecast_note='Process-duration forecast assumes all workers busy; pilot-wall extrapolation includes scheduling tails. The first ten sorted cohort domains and observed failures may not represent the remaining sites.',
                   peak_site_process_tree_rss_bytes=max([int(r['peak_rss_bytes']) for r in selected_rows if r['peak_rss_bytes'] != ''], default=None),
                   memory_measurement='Sampled RSS includes each site process and descendants. It is not aggregate unified memory.',
                   storage_note='Monitor stops before the ceiling with per-worker headroom; a single large browser write can exceed headroom.')
    (DATA / ('pilot-summary.json' if args.pilot else 'full-summary.json')).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if summary['budget_exceeded_bytes']:
        raise SystemExit('Crawl stopped but in-flight writes exceeded the output budget. Raw evidence was retained; inspect the summary before further work.')


def main():
    import sys
    if '--self-test' in sys.argv:
        main_inner()
        return
    DATA.mkdir(parents=True, exist_ok=True)
    lock = DATA / '.run-lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise SystemExit('Another crawl/export owns data/.run-lock. If its process ended, remove this empty lock directory.')
    try:
        main_inner()
    finally:
        lock.rmdir()


if __name__ == '__main__':
    main()
