#!/usr/bin/env python3
"""Build a separate results database and compare domain-level collection rates."""
import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import math
import os
import sqlite3
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {'identifying_pi': {'Address', 'EmailAddress', 'GovernmentId', 'BankAccountNumber',
                             'PersonName', 'PhoneNumber', 'UsernameOrOtherId', 'TaxId'}}
PAPER_TYPES = ['EmailAddress', 'PhoneNumber', 'PersonName', 'Address', 'LocationCityOrCoarser',
               'PostalCode', 'AgeOrAgeGroup', 'DateOfBirth', 'BankAccountNumber', 'GovernmentId',
               'TaxId', 'UsernameOrOtherId', 'Ethnicity', 'Gender', 'CitizenshipOrImmigrationStatus', 'MilitaryStatus']
PARENT_CATEGORIES = {'Government & Politics', 'Health', 'Shopping & Auctions',
                     'Society & Lifestyle', 'Internet Communication'}
FIGURE_CATEGORIES = ['Gaming', 'Video Streaming', 'Internet Communication', 'News & Media',
                     'Society & Lifestyle', 'Shopping & Auctions', 'Travel', 'Economy & Finance',
                     'Health', 'Government & Politics', 'Educational Institutions']
FIGURE_PURPOSES = ['Role Application Form', 'Financial Application Form', 'Payment Form',
                   'Reservation Form', 'Contact Form', 'Content Submission Form', 'Subscription Form',
                   'Account Registration Form', 'Account Login Form', 'Account Recovery Form', 'Unknown']
RARE_FIGURE_TYPES = ['DateOfBirth', 'AgeOrAgeGroup', 'BankAccountNumber', 'TaxId', 'GovernmentId',
                    'Gender', 'CitizenshipOrImmigrationStatus', 'Ethnicity', 'MilitaryStatus']
RARE_FIGURE_NAMES = ['Date of birth', 'Age', 'Bank account number', 'Tax ID', 'Government ID',
                    'Gender', 'Citizenship / immigration status', 'Ethnicity', 'Military status']


def jsonl(path):
    with Path(path).open() as h:
        return [json.loads(line) for line in h if line.strip()]


def csv_rows(path):
    with Path(path).open() as h:
        return list(csv.DictReader(h))


def taxonomy(relative):
    tree = ast.parse((ROOT/'upstream'/relative).read_text())
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'LABELS' for t in n.targets))


def categories(sites, category_names=None):
    raw = {s['domain']: json.loads(s['categories']) for s in sites}
    names = {i['id']: i['name'] for items in raw.values() for i in items}
    names.update({int(k): v for k, v in (category_names or {}).items()})
    result = {}
    for domain, items in raw.items():
        result[domain] = set()
        for item in items:
            # Reproduce the notebook's subcategory rows and selected parent mapping.
            if 'super_category_id' not in item:
                continue
            parent = names.get(item['super_category_id'])
            result[domain].add(parent if parent in PARENT_CATEGORIES else item['name'])
        if not items:
            result[domain].add('Unknown')
    return result


def aggregate(records, domains):
    result = defaultdict(set)
    for domain, purpose, labels in records:
        if domain in domains and not SETTINGS['identifying_pi'].isdisjoint(labels):
            result[domain, purpose].update(labels)
    return result


def requiredness(control):
    required = bool(control.get('html_required')) or str(control.get('aria_required', '')).lower() == 'true' or bool(control.get('required_text'))
    optional = bool(control.get('optional_text')) or str(control.get('aria_required', '')).lower() == 'false'
    return 'conflict' if required and optional else 'required' if required else 'optional' if optional else 'unspecified'


def load_annotation(path=None):
    spec = importlib.util.spec_from_file_location('jev_annotation', path or ROOT/'03-annotate/run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    return module


def build_database(forms, predictions, output, group_eligible, allow_mock=False, annotation_module=None, verified_keys=None):
    form_labels = set(taxonomy('form-type-classification/utils.py')) | {'Unknown'}
    pi_labels = set(taxonomy('pi-type-classification/train-setfit-script.py'))
    lookup = {}
    identities = {}
    for form in forms:
        fid = form['form_id']
        if fid in identities:
            raise ValueError('Duplicate form_id in captures.')
        identities[fid] = ('form', form)
        for group in form['groups']:
            if group['group_id'] in identities:
                raise ValueError('Duplicate group_id in captures.')
            identities[group['group_id']] = ('group', form)
    annotation = annotation_module or load_annotation()
    purpose_labels, pi = annotation.taxonomies()
    expected_requests = {}
    for p in predictions:
        if p.get('mock') and not allow_mock:
            raise ValueError('Mock predictions cannot enter live analysis.')
        if p['id'] not in identities:
            # Earlier crawl attempts remain in append-only history, but do not join current captures.
            continue
        kind, form = identities[p['id']]
        if (p['kind'] != kind or any(p.get(k) != form[k] for k in ('domain','form_id','job_hash','form_filename'))
                or (kind == 'group' and p.get('group_id') != p['id'])):
            raise ValueError('Prediction identity/context mismatch.')
        threshold = p.get('threshold')
        if not isinstance(threshold, (int, float)):
            raise ValueError('Prediction threshold is missing.')
        if verified_keys is not None:
            expected = verified_keys.get(p['id'])
            if p.get('cache_key') != expected:
                raise ValueError('Hybrid prediction differs from verified lineage.')
            allowed = form_labels if kind == 'form' else pi_labels
            if p.get('status') == 'ok' and (not isinstance(p.get('labels'), list) or not set(p['labels']) <= allowed or (kind == 'form' and len(p['labels']) != 1)):
                raise ValueError('Invalid hybrid prediction taxonomy.')
            lookup[p['id']] = p
            continue
        request_key = (form['form_id'], threshold)
        if request_key not in expected_requests:
            expected_requests[request_key] = {i['id']: annotation.cache_key(payload, threshold)
                for i, payload in annotation.tasks(form, purpose_labels, pi)}
        if p.get('cache_key') != expected_requests[request_key][p['id']]:
            # A repeated job identity can have changed evidence in a later crawl attempt.
            continue
        if p.get('status') == 'ok':
            allowed = form_labels if kind == 'form' else pi_labels
            if not isinstance(p['labels'], list) or not set(p['labels']) <= allowed:
                raise ValueError('Invalid prediction label type or taxonomy.')
            if kind == 'form' and len(p['labels']) != 1:
                raise ValueError('Form prediction must have one label.')
        lookup[p['id']] = p
    temporary = output.with_suffix('.tmp.db')
    if temporary.exists():
        temporary.unlink()
    con = sqlite3.connect(temporary)
    con.executescript('''
      CREATE TABLE form_classification(domain TEXT, job_hash TEXT, form_filename TEXT,
        form_type TEXT, scores TEXT, PRIMARY KEY(domain,job_hash,form_filename));
      CREATE TABLE field_classification(domain TEXT, job_hash TEXT, form_filename TEXT,
        field_list TEXT, PRIMARY KEY(domain,job_hash,form_filename));
      CREATE TABLE field_evidence(domain TEXT, form_id TEXT, group_id TEXT, field_id TEXT PRIMARY KEY,
        technical INTEGER, user_request INTEGER, html_required INTEGER, aria_required TEXT, required_text TEXT,
        optional_text TEXT, requiredness TEXT, evidence TEXT);
      CREATE TABLE annotation_state(form_id TEXT PRIMARY KEY, domain TEXT, state TEXT);
    ''')
    records, annotated, comparison_resolved = [], set(), set()
    for f in forms:
        fp = lookup.get(f['form_id'], {})
        eligible = [g for g in f['groups'] if group_eligible(g)]
        groups_known = all(lookup.get(g['group_id'], {}).get('status') == 'ok' for g in eligible)
        known = fp.get('status') == 'ok' and groups_known
        state = 'ok' if known else 'incomplete'
        con.execute('INSERT INTO annotation_state VALUES(?,?,?)', (f['form_id'], f['domain'], state))
        purpose = fp['labels'][0] if fp.get('status') == 'ok' else 'Unknown'
        key = (f['domain'], f['job_hash'], f['form_filename'])
        con.execute('INSERT INTO form_classification VALUES(?,?,?,?,?)', (*key, purpose, json.dumps(fp.get('probabilities', {}))))
        labels = set()
        for group in f['groups']:
            gp = lookup.get(group['group_id'], {})
            if group_eligible(group) and gp.get('status') == 'ok':
                labels.update(gp['labels'])
            for c in group['controls']:
                technical = not c.get('visible') or c.get('type') == 'hidden'
                user_request = group_eligible({'controls': [c]})
                con.execute('INSERT INTO field_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (f['domain'], f['form_id'], group['group_id'], c['field_id'], int(technical), int(user_request),
                     int(bool(c.get('html_required'))), str(c.get('aria_required') or ''),
                     json.dumps(c.get('required_text', [])), json.dumps(c.get('optional_text', [])),
                     requiredness(c), json.dumps(c)))
        # PI annotation is independent of form-purpose uncertainty; NULL means unresolved PI.
        con.execute('INSERT INTO field_classification VALUES(?,?,?,?)', (*key, json.dumps(sorted(labels)) if groups_known else None))
        if known:
            annotated.add(f['form_id'])
        # Purpose uncertainty cannot affect a form excluded by identifying-PI filtering.
        resolved = groups_known and (SETTINGS['identifying_pi'].isdisjoint(labels) or fp.get('status') == 'ok')
        if resolved:
            comparison_resolved.add(f['form_id'])
            records.append((f['domain'], purpose, labels))
    con.commit()
    con.close()
    temporary.replace(output)
    return records, annotated, comparison_resolved


def request_keys(forms, annotation, threshold):
    purposes, pi = annotation.taxonomies()
    return {identity['id']: annotation.cache_key(payload, threshold)
            for form in forms for identity, payload in annotation.tasks(form, purposes, pi)}


def hybrid_predictions(args, forms, replacements):
    """Validate each origin against its own frozen evidence and configuration."""
    manifest = json.loads(args.followup_manifest.read_text())
    for name, expected in manifest['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen source checksum mismatch: ' + name)
    if hashlib.sha256(args.forms.read_bytes()).hexdigest() != manifest['input_sha256']:
        raise ValueError('Frozen follow-up capture checksum mismatch.')
    entries = manifest['records']
    selected = {row['id']: row for row in entries}
    if len(selected) != len(entries):
        raise ValueError('Reannotation manifest contains duplicate identities.')
    baseline_forms = jsonl(args.baseline_forms)
    # Added context may not alter controls, identities, or the full capture universe.
    def capture_identity(form):
        return {key: form[key] for key in ('domain', 'form_id', 'job_hash', 'form_filename', 'groups')}
    if {f['form_id']: capture_identity(f) for f in forms} != {f['form_id']: capture_identity(f) for f in baseline_forms}:
        raise ValueError('Follow-up must preserve the full baseline capture universe and controls.')
    frozen = load_annotation(args.baseline_annotation)
    revised = load_annotation()
    if hasattr(revised, 'configure_v3'):
        revised.configure_v3()
    else:
        revised.PROMPT_VERSION = manifest['config']['prompt_version']
    config = manifest['config']
    if (config['model'] != revised.MODEL or config['prompt_version'] != revised.PROMPT_VERSION or
            config['review_margin'] != revised.REVIEW_MARGIN or config['form_threshold'] != revised.FORM_THRESHOLD):
        raise ValueError('Frozen follow-up configuration differs from annotation implementation.')
    old_keys = request_keys(baseline_forms, frozen, config['threshold'])
    new_keys = request_keys(forms, revised, config['threshold'])
    old = jsonl(args.baseline_predictions)
    baseline = {}
    for prediction in old:
        if prediction['id'] not in old_keys:
            continue
        if prediction.get('cache_key') == old_keys[prediction['id']]:
            if (prediction.get('prompt_version') != frozen.PROMPT_VERSION or prediction.get('threshold') != config['threshold'] or
                    (prediction.get('status') == 'ok' and prediction.get('model') != frozen.MODEL)):
                raise ValueError('Baseline prediction has inconsistent frozen configuration.')
            baseline[prediction['id']] = prediction
    lookup = dict(baseline)
    replaced = set()
    for prediction in replacements:
        identity = prediction['id']
        if identity not in selected:
            raise ValueError('Replacement is outside the frozen selection manifest.')
        entry = selected[identity]
        if (entry['cache_key'] != new_keys.get(identity) or entry['source_cache_key'] != old_keys.get(identity) or
                prediction.get('cache_key') != entry['cache_key']):
            raise ValueError('Replacement evidence hash or baseline lineage mismatch.')
        if (prediction.get('prompt_version') != config['prompt_version'] or prediction.get('threshold') != config['threshold'] or
                (prediction.get('status') == 'ok' and prediction.get('model') != config['model'])):
            raise ValueError('Replacement configuration differs from frozen manifest.')
        capture_identity = {key: prediction.get(key) for key in ('domain','job_hash','form_filename','form_id')}
        if prediction.get('source_cache_key') != entry['source_cache_key'] or prediction.get('capture_identity') != capture_identity:
            raise ValueError('Replacement prediction lacks matching source/capture provenance.')
        if prediction.get('payload_sha256') != entry.get('payload_sha256') or prediction.get('configuration_sha256') != hashlib.sha256(revised.canonical(config).encode()).hexdigest():
            raise ValueError('Replacement payload/configuration provenance mismatch.')
        lookup[identity] = prediction
        replaced.add(identity)
    # Even pending entries must validate to avoid an invalid manifest silently carrying forward.
    for identity, entry in selected.items():
        if entry['cache_key'] != new_keys.get(identity) or entry['source_cache_key'] != old_keys.get(identity):
            raise ValueError('Manifest evidence/configuration does not match frozen requests.')
    records = list(lookup.values())
    lineage = [{'id': identity, 'origin': 'v3_reannotated' if identity in replaced else 'v2_carried_forward',
                'cache_key': row['cache_key'], 'source_cache_key': old_keys[identity],
                'prompt_version': row.get('prompt_version'), 'status': row.get('status'),
                'selected_for_reannotation': identity in selected}
               for identity, row in sorted(lookup.items())]
    keys = {row['id']: row['cache_key'] for row in records}
    return records, keys, lineage, frozen


def database_records(path):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True) as con:
        rows = list(con.execute('SELECT domain,form_type,field_list FROM form_classification JOIN field_classification USING(domain,job_hash,form_filename)'))
    return [(d, purpose, set(json.loads(labels))) for d, purpose, labels in rows if labels is not None], rows


def coverage_summary(forms, predictions, annotation, complete):
    lookup = {row['id']: row for row in predictions}
    blocked_domains, pi_domains, purpose_domains = set(), set(), set()
    blocking_forms, unresolved_groups, purpose_blockers = 0, 0, 0
    for form in forms:
        if form['domain'] not in complete:
            continue
        eligible = [group for group in form['groups'] if annotation.eligible_group(group)]
        unresolved = [group for group in eligible if lookup.get(group['group_id'], {}).get('status') != 'ok']
        known_labels = {label for group in eligible for label in
                        lookup.get(group['group_id'], {}).get('labels', [])
                        if lookup.get(group['group_id'], {}).get('status') == 'ok'}
        purpose_blocked = bool(SETTINGS['identifying_pi'] & known_labels) and lookup.get(form['form_id'], {}).get('status') != 'ok'
        if unresolved or purpose_blocked:
            blocked_domains.add(form['domain']); blocking_forms += 1
        if unresolved:
            pi_domains.add(form['domain']); unresolved_groups += len(unresolved)
        if purpose_blocked:
            purpose_domains.add(form['domain']); purpose_blockers += 1
    return {'excluded_complete_domains': len(blocked_domains), 'blocking_forms_on_complete_domains': blocking_forms,
            'unresolved_eligible_groups_on_complete_domains': unresolved_groups,
            'currently_required_purpose_blockers_on_complete_domains': purpose_blockers,
            'domains_pi_only': len(pi_domains-purpose_domains), 'domains_purpose_only': len(purpose_domains-pi_domains),
            'domains_both': len(pi_domains & purpose_domains),
            'identity_status_counts': {kind: {state: sum(row['kind'] == kind and row.get('status') == state for row in lookup.values())
                                             for state in sorted({row.get('status', 'missing') for row in lookup.values()})}
                                       for kind in ['form','group']},
            'qualification': 'Purpose blockers require currently known identifying PI; PI resolution can expose purpose requirements.'}


def write_followup_comparison(args, compared, new, mapping, lineage):
    original, baseline_rows = database_records(args.baseline_results)
    complete = {s['domain'] for s in csv_rows(args.statuses) if s['status'] == 'complete'}
    unresolved = {d for d, purpose, labels in baseline_rows if labels is None or
                  (not SETTINGS['identifying_pi'].isdisjoint(json.loads(labels)) and purpose == 'Unknown')}
    baseline_domains = complete - unresolved
    matched = baseline_domains & compared
    rows = rate_rows('v2', 'original_matched', matched, original, mapping)
    rows += rate_rows('v3_hybrid', 'original_matched', matched, new, mapping)
    write_csv(args.output/'baseline-followup-rates.csv', rows,
              ['dataset','cohort','category','form_type','pi_type','numerator','denominator','rate'])
    (args.output/'compared-domains.json').write_text(json.dumps(sorted(compared), indent=2)+'\n')
    (args.output/'lineage.jsonl').write_text(''.join(json.dumps(row, sort_keys=True)+'\n' for row in lineage))
    summary = {'protocol': 'Selective hybrid annotation, untouched records retain frozen v2 provenance.',
               'baseline_eligible_domains': len(baseline_domains), 'original_matched_domains': len(matched),
               'baseline_domains_excluded_now': sorted(baseline_domains-compared),
               'newly_eligible_domains': sorted(compared-baseline_domains),
               'revised_eligible_domains': len(compared),
               'origin_counts': {origin: sum(row['origin'] == origin for row in lineage)
                                 for origin in ['v2_carried_forward', 'v3_reannotated']},
               'origin_status_counts': {origin: {state: sum(row['origin'] == origin and row['status'] == state for row in lineage)
                                                for state in sorted({row['status'] for row in lineage})}
                                        for origin in ['v2_carried_forward','v3_reannotated']},
               'historical_comparison': 'rates.csv historical/compared and new/compared share exactly compared-domains.json.',
               'accuracy': 'Coverage and changed labels are diagnostic observations, not independently validated accuracy.'}
    frozen = load_annotation(args.baseline_annotation)
    baseline_forms = jsonl(args.baseline_forms)
    baseline_keys = request_keys(baseline_forms, frozen, .5)
    baseline_predictions = [row for row in jsonl(args.baseline_predictions) if row.get('cache_key') == baseline_keys.get(row['id'])]
    hybrid_lookup = {row['id']: row for row in baseline_predictions}
    hybrid_lookup.update({row['id']: row for row in jsonl(args.predictions)})
    summary['blockers'] = {'baseline': coverage_summary(baseline_forms, baseline_predictions, frozen, complete),
                           'followup': coverage_summary(baseline_forms, list(hybrid_lookup.values()), frozen, complete)}
    (args.output/'followup-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def historical(path, domains):
    con = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
    try:
        con.execute('PRAGMA query_only=ON')
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'form_classification', 'field_classification'} <= tables:
            raise ValueError('Historical database lacks annotation tables.')
        rows = con.execute('''SELECT domain,form_type,field_list FROM form_classification
            JOIN field_classification USING(domain,job_hash,form_filename)''')
        return [(d, p, set(json.loads(l))) for d, p, l in rows if d in domains and l is not None]
    finally:
        con.close()


def rate_rows(dataset, cohort, domains, records, mapping):
    agg = aggregate(records, domains)
    purposes = taxonomy('form-type-classification/utils.py') + ['Unknown']
    all_categories = sorted(set().union(*mapping.values())) if mapping else []
    rows = []
    for category in ['All'] + all_categories:
        category_domains = {d for d in domains if category == 'All' or category in mapping[d]}
        for purpose in ['All'] + purposes:
            denominator_domains = category_domains if purpose == 'All' else {d for d, p in agg if p == purpose and d in category_domains}
            denominator = len(denominator_domains)
            for pi in PAPER_TYPES:
                requested = {d for (d, p), labels in agg.items() if d in denominator_domains and
                             (purpose == 'All' or purpose == p) and pi in labels}
                rows.append({'dataset': dataset, 'cohort': cohort, 'category': category, 'form_type': purpose,
                             'pi_type': pi, 'numerator': len(requested), 'denominator': denominator,
                             'rate': len(requested)/denominator if denominator else ''})
        form_bearing = {d for d, p in agg if d in category_domains}
        for purpose in purposes:
            requested = {d for d, p in agg if d in category_domains and p == purpose}
            rows.append({'dataset': dataset, 'cohort': cohort, 'category': category, 'form_type': purpose,
                         'pi_type': 'form_purpose_presence', 'numerator': len(requested),
                         'denominator': len(form_bearing), 'rate': len(requested)/len(form_bearing) if form_bearing else ''})
    return rows


def write_csv(path, rows, fields):
    with path.open('w', newline='') as h:
        writer = csv.DictWriter(h, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analyze(args):
    start = time.monotonic()
    sites, statuses = csv_rows(args.sites), csv_rows(args.statuses)
    domains = {s['domain'] for s in sites}
    if len(domains) != len(sites):
        raise ValueError('Cohort contains duplicate domains.')
    if any(s['domain'] not in domains for s in statuses):
        raise ValueError('Status contains a domain outside the fixed cohort.')
    forms, predictions = jsonl(args.forms), jsonl(args.predictions)
    if any(p['domain'] not in domains for p in predictions):
        raise ValueError('Predictions contain a domain outside the fixed cohort.')
    if any(f['domain'] not in domains for f in forms):
        raise ValueError('Captures contain a domain outside the cohort.')
    args.output.mkdir(parents=True, exist_ok=True)
    annotation = load_annotation()
    # Agent integration resolves this exact shared eligibility function.
    group_eligible = annotation.eligible_group
    if args.allow_mock and args.output.resolve() == (ROOT/'05-analyze/data').resolve():
        raise ValueError('Fixture analysis requires a separate --output directory.')
    followup = bool(getattr(args, 'followup_manifest', None))
    lineage, verified_keys = None, None
    if followup:
        if args.output.resolve() == (ROOT/'05-analyze/data').resolve():
            raise ValueError('Follow-up analysis requires versioned --output.')
        predictions, verified_keys, lineage, frozen = hybrid_predictions(args, forms, predictions)
        group_eligible = frozen.eligible_group
    new, annotated, comparison_resolved = build_database(forms, predictions, args.output/'results.db', group_eligible, args.allow_mock, verified_keys=verified_keys)
    old = historical(args.historical, domains)
    manifest_path = args.sites.with_name('manifest.json')
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    mapping = categories(sites, manifest.get('category_names'))
    latest = {s['domain']: s for s in statuses}
    complete = {d for d, s in latest.items() if s['status'] == 'complete'}
    captures = defaultdict(set)
    for f in forms:
        captures[f['domain']].add(f['form_id'])
    for d in complete:
        if int(latest[d]['forms']) != len(captures.get(d, set())):
            raise ValueError('Complete-site form count differs from its normalized captures.')
    captured_ids = {f['form_id'] for f in forms} | {g['group_id'] for f in forms for g in f['groups']}
    ignored_ids = {p['id'] for p in predictions} - captured_ids
    latest_predictions = {p['id']: p for p in predictions if p['id'] in captured_ids}
    configurations = {(p.get('model'), p.get('prompt_version'), p.get('threshold')) for p in latest_predictions.values() if p.get('status') == 'ok'}
    if not followup and len(configurations) > 1:
        raise ValueError('Analysis requires one frozen prediction configuration.')
    compared = {d for d in complete if captures.get(d, set()) <= comparison_resolved}
    rates = rate_rows('historical', 'selected', domains, old, mapping)
    rates += rate_rows('historical', 'compared', compared, old, mapping)
    rates += rate_rows('new', 'compared', compared, new, mapping)
    write_csv(args.output/'rates.csv', rates, ['dataset', 'cohort', 'category', 'form_type', 'pi_type', 'numerator', 'denominator', 'rate'])
    old_agg, new_agg = aggregate(old, compared), aggregate(new, compared)
    differences = []
    for d in sorted(compared):
        for purpose in sorted({p for domain, p in set(old_agg)|set(new_agg) if domain == d}):
            before, after = old_agg.get((d, purpose), set()), new_agg.get((d, purpose), set())
            differences.append({'domain': d, 'form_type': purpose, 'historical_pi': json.dumps(sorted(before)),
                                'new_pi': json.dumps(sorted(after)), 'newly_observed_pi': json.dumps(sorted(after-before)),
                                'not_observed_now_pi': json.dumps(sorted(before-after))})
    write_csv(args.output/'differences.csv', differences, ['domain','form_type','historical_pi','new_pi','newly_observed_pi','not_observed_now_pi'])
    con = sqlite3.connect(args.output/'results.db')
    evidence = list(con.execute('SELECT technical,html_required,aria_required,required_text,optional_text,requiredness FROM field_evidence WHERE technical=1 OR user_request=1'))
    con.close()
    required = []
    for technical in (0, 1):
        subset = [r for r in evidence if r[0] == technical]
        conditions = {'html_declared_required': lambda r: bool(r[1]),
                      'aria_or_text_declared_required': lambda r: r[2].lower() == 'true' or bool(json.loads(r[3])),
                      'explicit_optional_signal': lambda r: r[2].lower() == 'false' or bool(json.loads(r[4])),
                      'unspecified': lambda r: r[5] == 'unspecified', 'conflict': lambda r: r[5] == 'conflict'}
        for signal, condition in conditions.items():
            n = sum(condition(r) for r in subset)
            required.append({'technical': technical, 'signal': signal, 'numerator': n, 'denominator': len(subset),
                             'rate': n/len(subset) if subset else ''})
    write_csv(args.output/'requiredness.csv', required, ['technical','signal','numerator','denominator','rate'])
    counts = {'selected': len(domains), 'attempted': len(latest),
              'reached': sum(int(s.get('pages',0) or 0)>0 for s in latest.values()),
              'complete': len(complete), 'partial': sum(s['status'] in {'partial','timeout','partial_timeout','interrupted','partial_interrupted','storage_limit'} for s in latest.values()),
              'form_bearing': len(captures), 'fully_annotated_form_domains': len({d for d in captures if captures[d] <= annotated}),
              'compared': len(compared), 'forms': len(forms), 'fully_annotated_forms': len(annotated),
              'comparison_resolved_forms': len(comparison_resolved),
              'comparison_resolved_form_domains': len({d for d in captures if captures[d] <= comparison_resolved}),
              'unjoined_annotation_identities': len(ignored_ids),
              'elapsed_seconds': round(time.monotonic()-start, 3)}
    if followup:
        counts['followup'] = write_followup_comparison(args, compared, new, mapping, lineage)
    (args.output/'counts.json').write_text(json.dumps(counts, indent=2)+'\n')
    readme = Path(__file__).with_name('README.md')
    marker = '\n<!-- measured-results -->\n'
    text = readme.read_text().split(marker)[0]
    text += marker + '\nLatest run compared '+str(len(compared))+' domains. Counts are in `data/counts.json`. '
    text += 'The analysis took '+str(counts['elapsed_seconds'])+' seconds. Human validation remains separate.\n'
    if not args.allow_mock and not followup:
        readme.write_text(text)
    return counts


def pipeline_self_test():
    import subprocess
    import sys
    def entry(step):
        spec = importlib.util.spec_from_file_location(step, ROOT/step/'run.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    crawl, validation = entry('02-crawl'), entry('04-validate')
    analysis = sys.modules[__name__]
    module = entry
    with tempfile.TemporaryDirectory(prefix='webform-integrated-') as t:
     p=Path(t)
     sites=[{'domain':f'site{i}.example','rank':i+1,'categories':'[]','start_url':f'https://site{i}.example'} for i in range(10)]
     with (p/'sites.csv').open('w',newline='') as h:
      w=csv.DictWriter(h,fieldnames=list(sites[0]));w.writeheader();w.writerows(sites)
     forms=[]
     for i in range(9):
      form={'fields':[{'name':'email','fieldElement':{'tagName':'INPUT','attributes':{'type':'email','required':'','value':'DO_NOT_SEND'},'isVisible':True},'labelElement':{'text':'Email'}}, {'name':'token','fieldElement':{'tagName':'INPUT','attributes':{'type':'hidden','value':'DO_NOT_SEND_TOKEN'},'isVisible':False}}], 'buttons':[{'text':'Register'}]}
      forms.append(crawl.normalize(sites[i]['domain'],'job','form-0.json',form,{'pageTitle':'Register duplicate' if i<2 else f'Register context{i}'}))
     (p/'forms.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in forms))
     assert 'DO_NOT_SEND' not in (p/'forms.jsonl').read_text()
     cmd=[str(ROOT/'.venv/bin/python'),str(ROOT/'03-annotate/run.py'),'--mock','--input',str(p/'forms.jsonl'),'--output',str(p/'predictions.jsonl')]
     subprocess.run(cmd,check=True)
     initial=(p/'predictions.jsonl').read_bytes();subprocess.run(cmd,check=True);assert initial==(p/'predictions.jsonl').read_bytes()
     with (p/'statuses.csv').open('w',newline='') as h:
      w=csv.DictWriter(h,fieldnames=['domain','status','forms','pages']);w.writeheader();w.writerows([{'domain':s['domain'],'status':'partial_timeout' if i==8 else 'complete','forms':1 if i<9 else 0,'pages':1} for i,s in enumerate(sites)])
     with sqlite3.connect(p/'historical.db') as con:
      con.executescript('CREATE TABLE form_classification(domain TEXT,job_hash TEXT,form_filename TEXT,form_type TEXT); CREATE TABLE field_classification(domain TEXT,job_hash TEXT,form_filename TEXT,field_list TEXT);')
      for s in sites:
       con.execute('INSERT INTO form_classification VALUES(?,?,?,?)',(s['domain'],'oldjob','oldform','Contact Form'));con.execute('INSERT INTO field_classification VALUES(?,?,?,?)',(s['domain'],'oldjob','oldform','["EmailAddress"]'))
     manifest=validation.export(forms,p/'review'); assert ('site0.example' in manifest['development_domains'])==('site1.example' in manifest['development_domains'])
     assert all(not r['human_labels'] for r in csv.DictReader((p/'review/review.csv').open()))
     args=argparse.Namespace(sites=p/'sites.csv',statuses=p/'statuses.csv',forms=p/'forms.jsonl',predictions=p/'predictions.jsonl',historical=p/'historical.db',output=p/'analysis',allow_mock=True)
     result=analysis.analyze(args);assert result['compared']==9 and result['partial']==1,result
     assert result['form_bearing']==9, 'Zero-form complete site counted as form-bearing'
     rates=list(csv.DictReader((p/'analysis/rates.csv').open()))
     r=next(r for r in rates if r['dataset']=='new' and r['category']=='All' and r['form_type']=='All' and r['pi_type']=='EmailAddress');assert (r['numerator'],r['denominator'])==('8','9'),r
     con=sqlite3.connect(p/'analysis/results.db');assert con.execute('SELECT count(*) FROM field_evidence').fetchone()[0]==18;con.close()
     try:
      analysis.build_database(forms,[json.loads(l) for l in initial.splitlines()],p/'rejected.db',module('03-annotate').eligible_group)
     except ValueError as e:
      assert 'Mock' in str(e)
     else:raise AssertionError('Mocks entered live results')
     # Four complete sites: technical only, confident nonidentifying PI,
     # unresolved PI, and identifying PI with unresolved purpose.
     import copy
     coverage_forms = copy.deepcopy(forms[:4])
     annotation = load_annotation()
     form_taxonomy, pi_taxonomy = annotation.taxonomies()
     predictions = []
     for i, form in enumerate(coverage_forms):
      if i == 0:
       for group in form['groups']:
        for control in group['controls']:
         control['visible'] = False
      for identity, payload in annotation.tasks(form, form_taxonomy, pi_taxonomy):
       is_form = identity['kind'] == 'form'
       eligible = payload is not None
       state = 'review' if is_form or not eligible or i == 2 else 'ok'
       labels = ['Unknown'] if is_form else ['EmailAddress'] if eligible and i == 3 else []
       predictions.append(dict(identity, cache_key=annotation.cache_key(payload, .5),
                               threshold=.5, status=state, labels=labels, probabilities={},
                               mock=True, model='fixture', prompt_version='fixture'))
     (p/'forms.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in coverage_forms))
     (p/'predictions.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in predictions))
     with (p/'statuses.csv').open('w', newline='') as h:
      w=csv.DictWriter(h,fieldnames=['domain','status','forms','pages']);w.writeheader()
      w.writerows({'domain':f['domain'],'status':'complete','forms':1,'pages':1} for f in coverage_forms)
     args.output=p/'coverage-analysis'
     coverage=analysis.analyze(args)
     assert coverage['fully_annotated_forms']==0 and coverage['comparison_resolved_forms']==2,coverage
     assert coverage['compared']==2,coverage
     rates=list(csv.DictReader((args.output/'rates.csv').open()))
     row=next(r for r in rates if r['dataset']=='new' and r['category']=='All' and r['form_type']=='All' and r['pi_type']=='EmailAddress')
     assert (row['numerator'],row['denominator'])==('0','2'),row
     with sqlite3.connect(args.output/'results.db') as con:
      assert con.execute("SELECT count(*) FROM annotation_state WHERE state='incomplete'").fetchone()[0]==4
      fields=dict(con.execute('SELECT domain,field_list FROM field_classification'))
      assert fields[coverage_forms[0]['domain']]=='[]'
      assert fields[coverage_forms[1]['domain']]=='[]'
      assert fields[coverage_forms[2]['domain']] is None
      assert json.loads(fields[coverage_forms[3]['domain']])==['EmailAddress']
     print('Combined fixture passed, including technical-only and confident nonidentifying exclusions without treating unresolved PI or identifying purpose as absent.')


def hybrid_self_test():
    """Exercise selective replacement without losing complete/zero-form accounting."""
    import copy
    import shutil
    frozen_path = ROOT/'05-analyze/data/methodology-v3/baseline-snapshot/03-annotate/run.py'
    if not frozen_path.exists():
        # Standalone installations still verify a frozen local source copy.
        frozen_path = ROOT/'03-annotate/run.py'
    with tempfile.TemporaryDirectory(prefix='webform-hybrid-') as temporary:
        p = Path(temporary)
        shutil.copyfile(frozen_path, p/'baseline-run.py')
        frozen = load_annotation(p/'baseline-run.py')
        revised = load_annotation()
        if hasattr(revised, 'configure_v3'):
            revised.configure_v3()
        else:
            revised.PROMPT_VERSION = 'europe-500-v3'
        forms = []
        for i in range(3):
            form = {'domain': f'site{i}.example', 'form_id': f'f{i}', 'job_hash': f'job{i}',
                    'form_filename': f'form{i}.json', 'page_title': 'Contact', 'buttons': ['Send'],
                    'groups': [{'group_id': f'g{i}', 'controls': [{'field_id': f'c{i}',
                                'visible': True, 'tag': 'input', 'type': 'email', 'name': 'email',
                                'labels': ['Email'], 'html_required': False}]}]}
            forms.append(form)
        old_keys = request_keys(forms, frozen, .5)
        new_keys = request_keys(forms, revised, .5)
        predictions = []
        purpose_taxonomy, pi = frozen.taxonomies()
        for form in forms:
            for identity, payload in frozen.tasks(form, purpose_taxonomy, pi):
                review = identity['id'] in {'g1', 'g2'}
                predictions.append(dict(identity, labels=['Contact Form'] if identity['kind'] == 'form' else ['EmailAddress'],
                                        status='review' if review else 'ok', cache_key=old_keys[identity['id']],
                                        threshold=.5, model=frozen.MODEL, prompt_version=frozen.PROMPT_VERSION,
                                        probabilities={}, mock=True))
        replacement = dict(next(row for row in predictions if row['id'] == 'g1'),
                           status='ok', cache_key=new_keys['g1'], prompt_version=revised.PROMPT_VERSION)
        manifest = {'config': {'model': revised.MODEL, 'prompt_version': revised.PROMPT_VERSION,
                              'threshold': .5, 'review_margin': revised.REVIEW_MARGIN, 'form_threshold': revised.FORM_THRESHOLD},
                    'records': [{'id': 'g1', 'cache_key': new_keys['g1'], 'source_cache_key': old_keys['g1']}]}
        manifest['source_sha256'] = {}
        manifest['records'][0]['payload_sha256'] = 'fixture-payload'
        replacement.update(source_cache_key=old_keys['g1'], payload_sha256='fixture-payload',
                           configuration_sha256=hashlib.sha256(revised.canonical(manifest['config']).encode()).hexdigest(),
                           capture_identity={key: replacement[key] for key in ('domain','job_hash','form_filename','form_id')})
        for name, rows in [('forms', forms), ('baseline', predictions), ('replacements', [replacement])]:
            (p/(name+'.jsonl')).write_text(''.join(json.dumps(row)+'\n' for row in rows))
        manifest['input_sha256'] = hashlib.sha256((p/'forms.jsonl').read_bytes()).hexdigest()
        (p/'manifest.json').write_text(json.dumps(manifest))
        args = argparse.Namespace(followup_manifest=p/'manifest.json', baseline_annotation=p/'baseline-run.py',
                                  baseline_forms=p/'forms.jsonl', baseline_predictions=p/'baseline.jsonl', forms=p/'forms.jsonl')
        rows, keys, lineage, baseline_module = hybrid_predictions(args, forms, [replacement])
        assert sum(row['origin'] == 'v3_reannotated' for row in lineage) == 1
        assert sum(row['origin'] == 'v2_carried_forward' for row in lineage) == 5
        assert next(row for row in rows if row['id'] == 'g2')['status'] == 'review'
        records, annotated, resolved = build_database(forms, rows, p/'results.db', baseline_module.eligible_group,
                                                      allow_mock=True, verified_keys=keys)
        assert resolved == {'f0', 'f1'}, resolved
        sites = [{'domain': f'site{i}.example', 'categories': '[]'} for i in range(4)]
        write_csv(p/'sites.csv', sites, ['domain', 'categories'])
        statuses = [{'domain': f'site{i}.example', 'status': 'complete', 'forms': 1 if i<3 else 0, 'pages': 1}
                    for i in range(4)]
        write_csv(p/'statuses.csv', statuses, ['domain','status','forms','pages'])
        with sqlite3.connect(p/'historical.db') as con:
            con.executescript('CREATE TABLE form_classification(domain TEXT,job_hash TEXT,form_filename TEXT,form_type TEXT); CREATE TABLE field_classification(domain TEXT,job_hash TEXT,form_filename TEXT,field_list TEXT);')
        build_database(forms, predictions, p/'baseline-results.db', frozen.eligible_group, allow_mock=True,
                       annotation_module=frozen)
        args.sites=p/'sites.csv'; args.statuses=p/'statuses.csv'; args.forms=p/'forms.jsonl'
        args.predictions=p/'replacements.jsonl'; args.historical=p/'historical.db'; args.output=p/'analysis'
        args.allow_mock=True; args.baseline_results=p/'baseline-results.db'
        result = analyze(args)
        assert result['compared'] == 3 and result['form_bearing'] == 3, result
        summary = result['followup']
        assert summary['baseline_eligible_domains'] == 2 and summary['original_matched_domains'] == 2
        assert summary['newly_eligible_domains'] == ['site1.example']
        for invalid in [dict(replacement, cache_key='mismatch'), dict(replacement, id='g0'),
                        dict(replacement, prompt_version='wrong')]:
            try:
                hybrid_predictions(args, forms, [invalid])
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid replacement was accepted.')
        try:
            hybrid_predictions(args, forms[:1], [replacement])
        except ValueError:
            pass
        else:
            raise AssertionError('Subset captures were accepted as the complete universe.')
        print('Hybrid fixture passed: replacements, unchanged carry-forward, mismatch rejection, complete sites and zero-form eligibility.')


def self_test():
    records = [('a','Contact Form',{'EmailAddress'}), ('a','Contact Form',{'PhoneNumber'}),
               ('b','Contact Form',{'Gender'}), ('c','Account Login Form',{'EmailAddress'})]
    agg = aggregate(records, {'a','b'})
    assert agg == {('a','Contact Form'): {'EmailAddress','PhoneNumber'}}
    rows = rate_rows('historical','selected',{'a','b'},records,{'a':{'Health'},'b':{'Health'}})
    r = next(r for r in rows if r['category']=='All' and r['form_type']=='All' and r['pi_type']=='EmailAddress')
    assert r['numerator'] == 1 and r['denominator'] == 2
    r = next(r for r in rows if r['category']=='All' and r['form_type']=='Contact Form' and r['pi_type']=='EmailAddress')
    assert r['denominator'] == 1
    assert requiredness({'html_required': True, 'optional_text': ['optional']}) == 'conflict'
    assert requiredness({}) == 'unspecified'
    assert categories([{'domain':'a','categories':'[]'}]) == {'a':{'Unknown'}}
    pipeline_self_test()
    hybrid_self_test()
    print('Analysis self-test passed.')


def plot_figures(args):
    """Recreate Figures 4 and 5 from the saved analysis without paid processing."""
    started = time.monotonic()
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'webform-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from scipy import stats
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    import textwrap

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'pdf.fonttype': 42})
    out = args.output/'figures'
    out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect((args.output/'results.db').resolve().as_uri()+'?mode=ro', uri=True)
    rows = list(con.execute('SELECT domain,form_type,field_list FROM form_classification '
                            'JOIN field_classification USING(domain,job_hash,form_filename)'))
    con.close()
    unresolved = {d for d, purpose, fields in rows if fields is None or
                  (not SETTINGS['identifying_pi'].isdisjoint(json.loads(fields)) and purpose == 'Unknown')}
    complete = {s['domain'] for s in csv_rows(args.statuses) if s['status'] == 'complete'}
    compared = complete - unresolved
    counts = json.loads((args.output/'counts.json').read_text())
    assert len(compared) == counts['compared'], 'Plot cohort differs from saved analysis'
    sites = csv_rows(args.sites)
    selected = {s['domain'] for s in sites}
    manifest = json.loads(args.sites.with_name('manifest.json').read_text())
    mapping = categories(sites, manifest.get('category_names'))
    new = [(d, purpose, set(json.loads(fields))) for d, purpose, fields in rows if fields is not None]
    old = historical(args.historical, selected)
    saved_rates = {(r['dataset'], r['cohort'], r['category'], r['form_type'], r['pi_type']): r
                   for r in csv_rows(args.output/'rates.csv')}
    panels = [('new-compared', 'European follow-up', 'new', 'compared', compared, new),
              ('historical-compared', 'Historical matched baseline', 'historical', 'compared', compared, old),
              ('historical-selected', 'Historical selected cohort', 'historical', 'selected', selected, old)]
    contact = ['EmailAddress', 'PersonName', 'PhoneNumber', 'Address']
    all_cells, outputs = [], []

    def label(value):
        if value == 'All':
            return 'Any forms / all categories'
        return '\n'.join(textwrap.wrap(value.replace(' Form', ''), 19))

    def welch(k1, n1, k2, n2):
        # Same Bernoulli Welch calculation as upstream notebook cell 13.
        if min(n1, n2) <= 1:
            return None
        p1, p2 = k1/n1, k2/n2
        v1, v2 = p1*(1-p1)/(n1-1), p2*(1-p2)/(n2-1)
        if v1+v2 == 0:
            return None
        df = (v1+v2)**2 / (v1**2/(n1-1)+v2**2/(n2-1))
        return float(stats.t.sf(abs((p1-p2)/math.sqrt(v1+v2)), df)*2)

    def cell(agg, domains, category, purpose, pi):
        cat = {d for d in domains if category == 'All' or category in mapping[d]}
        den = cat if purpose == 'All' else {d for d, p in agg if d in cat and p == purpose}
        yes = {d for (d, p), types in agg.items() if d in den and
               (purpose == 'All' or p == purpose) and pi in types}
        if purpose == 'All':
            rest = domains-cat
            rest_yes = {d for (d, p), types in agg.items() if d in rest and pi in types}
        else:
            other = [(d, types) for (d, p), types in agg.items() if not (d in cat and p == purpose)]
            rest, rest_yes = {d for d, _ in other}, {d for d, types in other if pi in types}
        k, n = len(yes), len(den)
        return {'numerator': k, 'denominator': n, 'rate': k/n if n else None,
                'rest_numerator': len(rest_yes), 'rest_denominator': len(rest),
                'p_value': welch(k, n, len(rest_yes), len(rest))}

    def save(fig, stem, book):
        for ext in ['png', 'pdf']:
            fig.savefig(out/(stem+'.'+ext), dpi=220, facecolor='white')
            outputs.append(stem+'.'+ext)
        book.savefig(fig)
        plt.close(fig)

    with PdfPages(out/'paper-style-figures.pdf', metadata={'Title': 'European web forms: paper-style figures'}) as book:
        for slug, title, dataset, cohort, domains, records in panels:
            agg = aggregate(records, domains)
            # Reconcile every displayed count with the existing rate exports.
            for category in ['All']+FIGURE_CATEGORIES:
                for purpose in ['All']+FIGURE_PURPOSES:
                    for pi in contact+RARE_FIGURE_TYPES:
                        c = cell(agg, domains, category, purpose, pi)
                        saved = saved_rates.get((dataset, cohort, category, purpose, pi))
                        if saved is not None:
                            assert (c['numerator'], c['denominator']) == (int(saved['numerator']), int(saved['denominator']))

            fig, axes = plt.subplots(1, 2, figsize=(15, 8.5))
            colors = [plt.get_cmap('tab10')(i) for i in range(4)]
            contexts = [(list(reversed(FIGURE_CATEGORIES)), 'Website category'), (FIGURE_PURPOSES, 'Form purpose')]
            for ax, (names, axis_title) in zip(axes, contexts):
                y = np.arange(len(names))
                ns = []
                for i, pi in enumerate(contact):
                    cells = [cell(agg, domains, name if axis_title == 'Website category' else 'All',
                                  'All' if axis_title == 'Website category' else name, pi) for name in names]
                    ns = [c['denominator'] for c in cells]
                    bars = ax.barh(y+(i-1.5)*.18, [c['rate'] if c['rate'] is not None else 0 for c in cells],
                                   height=.17, color=colors[i], label=pi)
                    for bar, c in zip(bars, cells):
                        if 0 < c['denominator'] < 10:
                            bar.set_hatch('///')
                    base = cell(agg, domains, 'All', 'All', pi)
                    ax.axvline(base['rate'], color=colors[i], linestyle='--', linewidth=1)
                ax.set_yticks(y, [label(name)+f'\nn={n}' for name, n in zip(names, ns)])
                ax.invert_yaxis()
                ax.set_xlim(0, 1)
                ax.set_xticks(np.linspace(0, 1, 6), [f'{x:.0%}' for x in np.linspace(0, 1, 6)])
                ax.set_xlabel('Domain-level collection rate')
                ax.set_title(axis_title, fontsize=12, pad=12)
                ax.grid(axis='x', alpha=.15)
            handles = [Patch(facecolor=color, label=name) for color, name in zip(colors, ['Email address','Person name','Phone number','Address'])]
            handles += [Line2D([0],[0], color='black', linestyle='--', label='Overall cohort rate'),
                        Patch(facecolor='white', hatch='///', label='Small context: n < 10')]
            fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5,.925), ncol=6, frameon=False, fontsize=9)
            fig.suptitle(f'Figure 4 style | {title} | {len(domains)} domains', fontsize=16, y=.98)
            fig.text(.5,.025,'Category n = all cohort domains in that category; purpose n = domains with an identifying-PI form of that purpose.\n'
                     'Zero-support contexts are labeled n=0. Provisional annotations; geography, date and crawl depth differ.',
                     ha='center', fontsize=9)
            fig.subplots_adjust(left=.16, right=.98, top=.85, bottom=.13, wspace=.62)
            save(fig, 'figure-4-'+slug, book)

            fig, axes = plt.subplots(3, 3, figsize=(19, 15))
            heat_summary = []
            for panel_index, (ax, pi, pi_name) in enumerate(zip(axes.flat, RARE_FIGURE_TYPES, RARE_FIGURE_NAMES)):
                cats = ['All']+list(reversed(FIGURE_CATEGORIES))
                purposes = ['All']+FIGURE_PURPOSES
                matrix = [[cell(agg, domains, cat, purpose, pi) for cat in cats] for purpose in purposes]
                baseline = matrix[0][0]['rate']
                supported = [[c['denominator'] >= 10 and c['p_value'] is not None and c['p_value'] < .05
                              for c in row] for row in matrix]
                above = [[supported[i][j] and c['rate'] > baseline for j,c in enumerate(row)] for i,row in enumerate(matrix)]
                yy = [0]+[i for i in range(1,len(purposes)) if any(above[i])]
                xx = [0]+[j for j in range(1,len(cats)) if any(above[i][j] for i in range(len(purposes)))]
                data = np.full((len(yy),len(xx)), np.nan)
                shown = 0
                for y,i in enumerate(yy):
                    for x,j in enumerate(xx):
                        c = matrix[i][j]
                        visible = (i==j==0) or supported[i][j]
                        if not visible:
                            continue
                        data[y,x] = c['rate']/baseline if baseline else 1
                        shown += not (i==j==0)
                        ratio = data[y,x]
                        ax.text(x,y,f"{c['numerator']}/{c['denominator']}\n{c['rate']:.1%}",ha='center',va='center',
                                fontsize=9,zorder=3,color='white' if ratio >= 1.5 or ratio <= .2 else 'black')
                cmap = plt.get_cmap('RdYlGn').copy();cmap.set_bad('#f2f2f2')
                ax.imshow(np.ma.masked_invalid(data), cmap=cmap, vmin=0, vmax=2, aspect='auto', interpolation='nearest')
                ax.set_xticks(range(len(xx)), [label(cats[j]) if j else 'All\ncategories' for j in xx],rotation=30,ha='right',fontsize=8)
                ax.set_yticks(range(len(yy)), [label(purposes[i]) if i else 'Any forms' for i in yy],fontsize=8)
                ax.set_title(f'({chr(97+panel_index)}) {pi_name}'+f'\nOverall {matrix[0][0]["numerator"]}/{len(domains)} = {baseline:.1%}',fontsize=11,pad=12)
                if not shown:
                    ax.set_xlabel('No additional contexts pass the paper filters',fontsize=8,labelpad=8)
                for i,row in enumerate(matrix):
                    for j,c in enumerate(row):
                        visible = i in yy and j in xx and ((i==j==0) or supported[i][j])
                        all_cells.append(dict(dataset=slug, figure=5, pi_type=pi, category=cats[j], form_type=purposes[i],
                                              displayed=visible, **c))
                heat_summary.append({'pi_type':pi,'overall_numerator':matrix[0][0]['numerator'],
                                     'overall_denominator':len(domains),'displayed_context_cells':shown})
            fig.suptitle(f'Figure 5 style | {title} | {len(domains)} domains',fontsize=17,y=.98)
            fig.text(.5,.03,'Cells show collecting domains / context domains and percentage. Gray = masked, never a confirmed zero.\n'
                     'Paper notebook filters: context n >= 10, unadjusted Welch p < 0.05, keep rows/columns with a retained rate above the overall rate.\n'
                     'Colors: red 0x, yellow 1x, green 2x overall rate. A zero overall rate has no defined relative color and is shown neutrally.\n'
                     'Sparse, overlapping contexts and annotation uncertainty limit interpretation. These tests do not compare historical with European outcomes.',
                     ha='center',fontsize=9)
            fig.subplots_adjust(left=.10,right=.98,top=.9,bottom=.17,wspace=.70,hspace=1.3)
            save(fig,'figure-5-'+slug,book)
            outputs.append({'dataset':slug,'heatmap_support':heat_summary})
    write_csv(out/'figure-5-cells.csv',all_cells,
              ['dataset','figure','pi_type','category','form_type','displayed','numerator','denominator','rate','rest_numerator','rest_denominator','p_value'])
    summary = {'elapsed_seconds':round(time.monotonic()-started,3), 'matched_domains':len(compared),
               'selected_domains':len(selected),'outputs':outputs,'matplotlib':matplotlib.__version__,
               'upstream_commit':'a4f391d604e5cd557b881145b2a1cfd072e542d0',
               'method':'Notebook Figures 4 and 5, with explicit project cohort denominators including complete observed-zero sites. '
                        'No privacy-policy figure: those data are outside scope. Welch tests are descriptive, unadjusted, within each dataset; '
                        'not evidence of regional effects. Undefined zero-variance tests stay masked.',
               'verification':'Cohort reconciled with counts.json; every available context count reconciled with rates.csv.'}
    (out/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sites', type=Path, default=ROOT/'01-prepare/data/sites.csv')
    p.add_argument('--statuses', type=Path, default=ROOT/'02-crawl/data/statuses.csv')
    p.add_argument('--forms', type=Path, default=ROOT/'02-crawl/data/forms.jsonl')
    p.add_argument('--predictions', type=Path, default=ROOT/'03-annotate/data/predictions.jsonl')
    p.add_argument('--historical', type=Path, default=ROOT/'01-prepare/data/webform-data.db')
    p.add_argument('--output', type=Path, default=ROOT/'05-analyze/data')
    p.add_argument('--allow-mock', action='store_true', help='Only for fixture verification with a separate output directory')
    p.add_argument('--followup-manifest', type=Path, help='Frozen manifest for explicit v2 carry-forward/v3 replacements')
    p.add_argument('--baseline-annotation', type=Path, default=ROOT/'03-annotate/data/methodology-v3/baseline-run.py')
    p.add_argument('--baseline-forms', type=Path, default=ROOT/'02-crawl/data/forms.jsonl')
    p.add_argument('--baseline-predictions', type=Path, default=ROOT/'03-annotate/data/predictions.jsonl')
    p.add_argument('--baseline-results', type=Path, default=ROOT/'05-analyze/data/results.db')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--plots', action='store_true', help='Recreate paper Figures 4 and 5 using saved analysis outputs')
    args = p.parse_args()
    if args.self_test:
        self_test()
    elif args.plots:
        print(json.dumps(plot_figures(args), indent=2))
    else:
        print(json.dumps(analyze(args), indent=2))

if __name__ == '__main__':
    main()
