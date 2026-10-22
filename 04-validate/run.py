#!/usr/bin/env python3
"""Export blinded domain-separated review rows and evaluate supplied labels."""
import argparse
import csv
import hashlib
import json
import random
import tempfile
import time
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {'seed': 42, 'forms': 100, 'groups': 300, 'development_fraction': 0.25}


def read_jsonl(path):
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


@lru_cache(maxsize=1)
def annotation_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('review_annotation', ROOT/'03-annotate/run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def signatures(form):
    # Use the actual sanitized Jev request, including questions, model and context.
    module = annotation_module()
    purposes, pi = module.taxonomies()
    complete = dict(form)
    complete.setdefault('job_hash', 'fixture')
    complete.setdefault('form_filename', 'fixture.json')
    return {identity['id']: module.cache_key(payload, module.PI_THRESHOLD)
            for identity, payload in module.tasks(complete, purposes, pi) if payload is not None}


def export(forms, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'review.csv').exists():
        raise ValueError('Review CSV already exists. Preserve human work or choose another output directory.')
    domains = sorted({f['domain'] for f in forms})
    parent = {d: d for d in domains}
    def find(d):
        while parent[d] != d:
            parent[d] = parent[parent[d]]
            d = parent[d]
        return d
    seen = {}
    request_signatures = {f['form_id']: signatures(f) for f in forms}
    for form in forms:
        for sig in request_signatures[form['form_id']].values():
            if sig in seen:
                parent[find(form['domain'])] = find(seen[sig])
            seen[sig] = form['domain']
    components = {}
    for d in domains:
        components.setdefault(find(d), []).append(d)
    parts = list(components.values())
    rng = random.Random(SETTINGS['seed'])
    rng.shuffle(parts)
    dev = set()
    for part in parts:
        if len(dev) < max(1, round(len(domains) * SETTINGS['development_fraction'])):
            dev.update(part)
    candidates = sorted(forms, key=lambda f: f['form_id'])
    rng.shuffle(candidates)
    chosen = candidates[:SETTINGS['forms']]
    rows, used_groups = [], 0
    for f in chosen:
        base = {'split': 'development' if f['domain'] in dev else 'evaluation', 'domain': f['domain'],
                'form_id': f['form_id'], 'page_title': f.get('page_title', ''),
                'buttons': json.dumps(f.get('buttons', [])), 'duplicate_signature': request_signatures[f['form_id']][f['form_id']]}
        rows.append(dict(base, kind='form', id=f['form_id'], evidence=json.dumps(f['groups']),
                         human_labels='', human_requiredness='', reviewer='', notes=''))
        for group in f['groups']:
            if used_groups >= SETTINGS['groups']:
                break
            if not annotation_module().eligible_group(group):
                continue
            group_base = dict(base, duplicate_signature=request_signatures[f['form_id']].get(group['group_id'], 'ineligible:'+group['group_id']))
            rows.append(dict(group_base, kind='group', id=group['group_id'], evidence=json.dumps(group['controls']),
                             human_labels='', human_requiredness='', reviewer='', notes=''))
            used_groups += 1
    with (output / 'review.csv').open('w', newline='') as h:
        writer = csv.DictWriter(h, fieldnames=list(rows[0]) if rows else [
            'split', 'domain', 'form_id', 'page_title', 'buttons', 'duplicate_signature',
            'kind', 'id', 'evidence', 'human_labels', 'human_requiredness', 'reviewer', 'notes'])
        writer.writeheader()
        writer.writerows(rows)
    manifest = {'seed': SETTINGS['seed'], 'forms': len(chosen), 'groups': used_groups,
                'development_domains': sorted(dev), 'evaluation_domains': sorted(set(domains) - dev),
                'duplicate_components': parts, 'status': 'pending human labels',
                'split_warning': 'No evaluation domains after duplicate grouping' if not set(domains)-dev else None,
                'labels_format': 'JSON array; [] means no PI; ["Unknown"] means unresolvable',
                'requiredness_format': 'JSON object mapping field_id to required, optional, unspecified, or conflict'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def evaluate(review, predictions, freeze, output, forms=None):
    frozen = json.loads(Path(freeze).read_text())
    if not frozen.get('prompt_version') or not isinstance(frozen.get('threshold'), (int, float)) or not frozen.get('frozen_at'):
        raise ValueError('Freeze file needs prompt_version, threshold and frozen_at before held-out evaluation.')
    from datetime import datetime
    frozen_at = datetime.fromisoformat(frozen['frozen_at'].replace('Z', '+00:00'))
    if frozen_at.tzinfo is None:
        raise ValueError('frozen_at needs a timezone.')
    with Path(review).open() as h:
        rows = list(csv.DictReader(h))
    dev_signatures = {r['duplicate_signature'] for r in rows if r['split'] == 'development'}
    evaluation = [r for r in rows if r['split'] == 'evaluation']
    if dev_signatures & {r['duplicate_signature'] for r in evaluation}:
        raise ValueError('Exact duplicate contexts cross the development/evaluation boundary.')
    purposes, pi = annotation_module().taxonomies()
    allowed_labels = {'form': set(purposes), 'group': set(pi) | {'Unknown'}}
    pred = {}
    for p in predictions:
        if p.get('mock'):
            raise ValueError('Mock predictions cannot enter human validation metrics.')
        pred[p['id']] = p
    metrics = {}
    for kind in ('form', 'group'):
        selected = [r for r in evaluation if r['kind'] == kind]
        labeled = [r for r in selected if r['human_labels'].strip()]
        if not labeled:
            metrics[kind] = {'status': 'pending human labels', 'selected': len(selected)}
            continue
        counts, agreement, covered, unknown = {}, 0, 0, 0
        for row in labeled:
            truth = json.loads(row['human_labels'])
            if not isinstance(truth, list) or not all(isinstance(x, str) for x in truth):
                raise ValueError('human_labels must be a JSON string array.')
            if not set(truth) <= allowed_labels[kind] or ('Unknown' in truth and truth != ['Unknown']):
                raise ValueError('Human labels must use the exact source taxonomy; Unknown must stand alone.')
            p = pred.get(row['id'], {})
            if forms is not None:
                captured = {f['form_id']: f for f in forms}
                if row['form_id'] not in captured:
                    raise ValueError('Review row has no current captured form.')
                current_signatures = signatures(captured[row['form_id']])
                if current_signatures.get(row['id']) != row['duplicate_signature']:
                    raise ValueError('Review evidence differs from current capture input.')
                annotation = annotation_module()
                form_types, pi_types = annotation.taxonomies()
                expected = {i['id']: annotation.cache_key(payload, frozen['threshold'])
                    for i, payload in annotation.tasks(captured[row['form_id']], form_types, pi_types)}
                if p and p.get('cache_key') != expected.get(row['id']):
                    raise ValueError('Prediction request differs from blinded review evidence.')
            if p and (p.get('prompt_version') != frozen['prompt_version'] or p.get('threshold') != frozen['threshold']):
                raise ValueError('Prediction differs from frozen settings.')
            guess = set(p.get('labels', [])) if p.get('status') == 'ok' else {'Unknown'}
            truth = set(truth)
            if kind == 'form' and len(truth) != 1:
                raise ValueError('Each form needs exactly one human purpose label.')
            unknown += 'Unknown' in guess
            covered += p.get('status') == 'ok' and 'Unknown' not in guess
            agreement += guess == truth
            for label in truth | guess:
                c = counts.setdefault(label, {'support': 0, 'tp': 0, 'fp': 0, 'fn': 0})
                c['support'] += label in truth
                c['tp'] += label in truth and label in guess
                c['fp'] += label not in truth and label in guess
                c['fn'] += label in truth and label not in guess
        # Include unsupported source classes with null scores, not fictitious accuracy.
        import ast
        source = ROOT / 'upstream' / ('form-type-classification/utils.py' if kind == 'form' else 'pi-type-classification/train-setfit-script.py')
        tree = ast.parse(source.read_text())
        labels = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'LABELS' for t in n.targets))
        for label in labels + ['Unknown']:
            counts.setdefault(label, {'support': 0, 'tp': 0, 'fp': 0, 'fn': 0})
        for c in counts.values():
            c['precision'] = c['tp'] / (c['tp'] + c['fp']) if c['tp'] + c['fp'] else None
            c['recall'] = c['tp'] / c['support'] if c['support'] else None
            c['f1'] = 2*c['tp'] / (2*c['tp'] + c['fp'] + c['fn']) if c['support'] else None
        supported = [c['f1'] for c in counts.values() if c['support']]
        metrics[kind] = {'selected': len(selected), 'human_labeled': len(labeled), 'per_class': counts,
                         'macro_f1_supported_classes': sum(supported)/len(supported) if supported else None,
                         'exact_label_set_agreement': agreement/len(labeled), 'coverage': covered/len(labeled),
                         'unknown_review_fraction': unknown/len(labeled)}
    checks, disagreements, confusion = 0, 0, {}
    if forms is not None:
        controls = {c['field_id']: c for f in forms for g in f['groups'] for c in g['controls']}
        for row in evaluation:
            if row['kind'] != 'group' or not row.get('human_requiredness', '').strip():
                continue
            human = json.loads(row['human_requiredness'])
            if not isinstance(human, dict):
                raise ValueError('human_requiredness must be an object keyed by field_id.')
            row_fields = {c['field_id'] for c in json.loads(row['evidence'])}
            for field_id, truth in human.items():
                if field_id not in row_fields or field_id not in controls:
                    raise ValueError('Requiredness check does not join to this captured group.')
                if truth not in {'required', 'optional', 'unspecified', 'conflict'}:
                    raise ValueError('Invalid requiredness label.')
                c = controls[field_id]
                required = bool(c.get('html_required')) or str(c.get('aria_required', '')).lower() == 'true' or bool(c.get('required_text'))
                optional = bool(c.get('optional_text')) or str(c.get('aria_required', '')).lower() == 'false'
                guess = 'conflict' if required and optional else 'required' if required else 'optional' if optional else 'unspecified'
                checks += 1
                disagreements += guess != truth
                pair = truth + ' / ' + guess
                confusion[pair] = confusion.get(pair, 0) + 1
    metrics['requiredness'] = {'status': 'evaluated' if checks else 'pending human checks',
                              'checked_controls': checks, 'disagreements': disagreements,
                              'disagreement_rate': disagreements/checks if checks else None,
                              'human_then_extracted_counts': confusion}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
    return metrics


def self_test():
    forms = [{'domain': d, 'form_id': d, 'page_title': title, 'buttons': [], 'groups': []}
             for d, title in [('a', 'Login'), ('b', 'Login'), ('c', 'Contact'), ('d', 'Payment')]]
    with tempfile.TemporaryDirectory() as t:
        export(forms, t)
        manifest = json.loads((Path(t)/'manifest.json').read_text())
        assert ('a' in manifest['development_domains']) == ('b' in manifest['development_domains'])
        rows = list(csv.DictReader((Path(t)/'review.csv').open()))
        assert all(not r['human_labels'] for r in rows)
        try:
            export(forms, t)
            raise AssertionError('Overwrite accepted')
        except ValueError:
            pass
    # Exercise metrics and requiredness joins with supplied synthetic truth.
    model = annotation_module()
    forms = [{'domain': d, 'job_hash': 'job', 'form_filename': 'form.json', 'form_id': d,
              'page_title': 'Contact '+d, 'buttons': ['Contact'], 'groups': [{'group_id': d+'-group',
              'controls': [{'field_id': d+'-field', 'name': 'email', 'label': 'Email', 'type': 'email',
              'visible': True, 'html_required': True, 'aria_required': 'false'}]}]}
             for d in ['a', 'b', 'c', 'd']]
    with tempfile.TemporaryDirectory() as t:
        output = Path(t)
        export(forms, output)
        review = output/'review.csv'
        rows = list(csv.DictReader(review.open()))
        for row in rows:
            row['human_labels'] = json.dumps(['Contact Form'] if row['kind'] == 'form' else ['EmailAddress'])
            if row['kind'] == 'group':
                row['human_requiredness'] = json.dumps({row['domain']+'-field': 'conflict'})
        with review.open('w', newline='') as h:
            writer = csv.DictWriter(h, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        predictions = [dict(kind=r['kind'], id=r['id'], status='ok', labels=json.loads(r['human_labels']),
                            prompt_version=model.PROMPT_VERSION, threshold=model.PI_THRESHOLD, cache_key=r['duplicate_signature']) for r in rows]
        freeze = output/'freeze.json'
        freeze.write_text(json.dumps({'prompt_version': model.PROMPT_VERSION, 'threshold': model.PI_THRESHOLD,
                                      'frozen_at': '2026-10-09T00:00:00+02:00'}))
        result = evaluate(review, predictions, freeze, output, forms)
        assert result['group']['macro_f1_supported_classes'] == 1
        assert result['requiredness']['checked_controls'] == 3 and result['requiredness']['disagreements'] == 0
        assert result['group']['per_class']['Fingerprints']['recall'] is None
        rows[0]['human_labels'] = '["EmailAdress"]'
        rows[0]['split'] = 'evaluation'
        # Invalid labels must fail instead of creating a class with invented support.
        with review.open('w', newline='') as h:
            writer = csv.DictWriter(h, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        try:
            evaluate(review, predictions, freeze, output, forms)
            raise AssertionError('Invalid human taxonomy accepted')
        except ValueError:
            pass
    print('Validation self-test passed.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['export', 'evaluate'], nargs='?', default='export')
    p.add_argument('--forms', type=Path, default=ROOT/'02-crawl/data/forms.jsonl')
    p.add_argument('--predictions', type=Path, default=ROOT/'03-annotate/data/predictions.jsonl')
    p.add_argument('--review', type=Path, default=ROOT/'04-validate/data/review.csv')
    p.add_argument('--freeze', type=Path, default=ROOT/'04-validate/data/freeze.json')
    p.add_argument('--output', type=Path, default=ROOT/'04-validate/data')
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    started = time.monotonic()
    result = export(read_jsonl(args.forms), args.output) if args.command == 'export' else evaluate(args.review, read_jsonl(args.predictions), args.freeze, args.output, read_jsonl(args.forms))
    print(json.dumps(result, indent=2))
    print(f'Elapsed seconds: {time.monotonic()-started:.2f}')

if __name__ == '__main__':
    main()
