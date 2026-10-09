"""Fetch auditable public data and analyze it without filling missing observations."""
import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pypdf import PdfReader

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import numpy as np
from scipy import stats

BASE = Path(__file__).resolve().parent
RAW = BASE / 'data/raw'
DATA = BASE / 'data'
INDICATORS = {'SP.DYN.LE00.IN': 'years', 'NY.GNP.PCAP.CD': 'current USD, Atlas method',
              'NY.GNP.PCAP.PP.CD': 'current international dollars, PPP'}
SOURCES = {
 'us_income': 'https://www.census.gov/library/publications/2024/demo/p60-282.html',
 'jp_income': 'https://www.mhlw.go.jp/toukei/saikin/hw/k-tyosa/k-tyosa23/dl/03.pdf',
}

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def write_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

def session():
    s = requests.Session()
    s.headers['User-Agent'] = 'JapaneseDietResearch/1.0 (educational public-data analysis)'
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    return s

def fetch(start, end):
    RAW.mkdir(parents=True, exist_ok=True)
    manifest, rows, incomes = [], [], []
    s = session()
    def get(key, url, params=None):
        record = {'key': key, 'requested_url': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat()}
        manifest.append(record)
        try:
            r = s.get(url, params=params, timeout=(15, 90))
            record.update(url=r.url, http_status=r.status_code)
            r.raise_for_status()
            path = RAW / (key + ('.json' if params else '.pdf' if url.endswith('.pdf') else '.html'))
            path.write_bytes(r.content)
            record.update(file=str(path.relative_to(BASE)), sha256=hashlib.sha256(r.content).hexdigest(), status='ok')
            return r
        except requests.RequestException as e:
            record.update(status='error', error=str(e))
            return None
    for code, unit in INDICATORS.items():
        r = get(code, f'https://api.worldbank.org/v2/country/JPN;USA;WLD/indicator/{code}',
                {'format': 'json', 'date': f'{start}:{end}', 'per_page': 20000})
        if r is None:
            continue
        try:
            payload = r.json()
            if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[1], list):
                raise ValueError('Unexpected World Bank response')
            if int(payload[0]['pages']) != 1:
                raise ValueError('Response needs pagination; reduce year range')
            for item in payload[1]:
                rows.append({'country': item['countryiso3code'], 'year': int(item['date']),
                             'indicator': code, 'value': item['value'], 'unit': unit,
                             'source_type': 'fetched_world_bank', 'source_url': r.url,
                             'lastupdated': payload[0].get('lastupdated', '')})
        except (ValueError, KeyError, TypeError) as e:
            manifest[-1].update(status='parse_error', error=str(e))
    for key, url in SOURCES.items():
        r = get(key, url)
        if r is None:
            continue
        # HTML is parsed, and the exact matching context is retained for audit.
        if key == 'jp_income':
            try:
                text = ' '.join(page.extract_text() or '' for page in PdfReader(BytesIO(r.content)).pages)
                text = re.sub(r'\s+', ' ', text)
            except Exception as e:
                manifest[-1].update(status='parse_error', error=str(e))
                continue
        else:
            soup = BeautifulSoup(r.content, 'html.parser')
            for tag in soup(['script', 'style', 'nav']):
                tag.decompose()
            text = soup.get_text(' ', strip=True)
        (RAW / (key + '.txt')).write_text(text, encoding='utf-8')
        pattern = (r'Real median household income was\s*\$([\d,]+)\s*in\s*2023' if key == 'us_income'
                   else r'全世帯\s*」\s*が\s*(\d+)\s*万\s*(\d+)\s*千円')
        match = re.search(pattern, text)
        if not match:
            manifest[-1].update(status='parse_error', error='Expected income sentence absent; no value substituted')
            continue
        value = float(match.group(1).replace(',', ''))
        if key == 'jp_income':
            value += float(match.group(2)) / 10
        incomes.append({'country': 'USA' if key == 'us_income' else 'JPN',
                       'year': 2023 if key == 'us_income' else 2022,
                       'statistic': 'real_median_household_income' if key == 'us_income' else 'mean_household_income',
                       'value': value if key == 'us_income' else value * 10000,
                       'unit': '2023 USD' if key == 'us_income' else 'JPY',
                       'source_type': 'fetched_official_pdf' if key == 'jp_income' else 'fetched_official_html', 'source_url': r.url,
                       'evidence': text[max(0, match.start()-80):match.end()+180]})
    write_csv(DATA/'world_bank.csv', rows, ['country','year','indicator','value','unit','source_type','source_url','lastupdated'])
    write_csv(DATA/'official_income.csv', incomes, ['country','year','statistic','value','unit','source_type','source_url','evidence'])
    dump(DATA/'manifest.json', manifest)
    failures = [m for m in manifest if m['status'] != 'ok']
    print(f'World Bank rows: {len(rows)}; official income rows: {len(incomes)}; failures: {len(failures)}')
    return not failures

def analyze():
    with (DATA/'world_bank.csv').open(encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    def series(country, indicator):
        return {int(r['year']): float(r['value']) for r in rows
                if r['country'] == country and r['indicator'] == indicator and r['value'] != ''}
    output = {'notes': ['PPT figures and fetched figures are separate.',
                        'Time-series correlations are descriptive, not causal; p-values assume independence and are not reported.',
                        'National aggregates cannot identify individual diet effects.'], 'life_expectancy': {}, 'income_life_correlations': {}}
    for country in ['JPN','USA','WLD']:
        life = series(country,'SP.DYN.LE00.IN')
        if life:
            years = sorted(life)
            vals = np.array([life[y] for y in years])
            output['life_expectancy'][country] = {'n':len(vals), 'first_year':years[0], 'last_year':years[-1],
                'first':float(vals[0]), 'last':float(vals[-1]), 'mean_across_years':float(np.mean(vals)),
                'change_years':float(vals[-1]-vals[0])}
        income = series(country,'NY.GNP.PCAP.PP.CD')
        years = sorted(life.keys() & income.keys())
        if len(years) >= 3:
            x, y = np.array([income[t] for t in years]), np.array([life[t] for t in years])
            if np.ptp(x) and np.ptp(y):
                output['income_life_correlations'][country] = {'paired_years':years,
                    'pearson_r':float(stats.pearsonr(x,y).statistic), 'spearman_rho':float(stats.spearmanr(x,y).statistic)}
    j, w = series('JPN','SP.DYN.LE00.IN'), series('WLD','SP.DYN.LE00.IN')
    output['japan_world_gap'] = [{'year':y, 'gap_years':j[y]-w[y]} for y in sorted(j.keys() & w.keys())]
    output['ppt_arithmetic_only'] = {'japan_median_usd':5670000*0.0066,
        'japan_iqr_usd':56628-26994, 'usa_iqr_usd':127000-60300,
        'warning':'Three quartiles are not three samples; no t-test or reconstructed salary distribution.'}
    dump(DATA/'analysis.json', output)
    print('Analysis saved to data/analysis.json')

def extract(ppt):
    slides = {}
    with zipfile.ZipFile(ppt) as z:
        for name in z.namelist():
            m = re.fullmatch(r'ppt/slides/slide(\d+)\.xml', name)
            if m:
                slides[int(m[1])] = [e.text for e in ET.fromstring(z.read(name)).iter() if e.tag.endswith('}t') and e.text]
    dump(DATA/'ppt_text.json', slides)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['fetch','analyze','all','extract'])
    p.add_argument('--start', type=int, default=2000)
    p.add_argument('--end', type=int, default=2022)
    p.add_argument('--ppt', type=Path, default=BASE/'source/Japanese Diet.pptx')
    a = p.parse_args()
    if not 1960 <= a.start <= a.end <= datetime.now().year:
        p.error('Require 1960 <= start <= end <= current year')
    if a.command == 'extract':
        extract(a.ppt)
        return
    ok = True
    if a.command in ['fetch','all']:
        ok = fetch(a.start,a.end)
    if a.command in ['analyze','all']:
        analyze()
    if not ok:
        raise SystemExit('Partial failure: inspect data/manifest.json; successful results were retained.')

if __name__ == '__main__':
    main()
