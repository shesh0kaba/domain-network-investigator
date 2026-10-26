"""Compare saved public-site collections without network requests.

Usage: python compare_evidence.py run1 run2 --out comparison.json
Outputs evidence edges, not a claim of common ownership or a numerical probability.
"""
import argparse,collections,hashlib,json,re
from pathlib import Path
from urllib.parse import urlparse
from collect_public import Page

LIBRARY=re.compile(r'jquery|bootstrap|swiper|uikit|intlTelInput|normalize(?:\.min)?\.css|fbevents|cloudflare-static/(?:email-decode|rocket-loader)',re.I)

def form_sig(form):
    a=form.get('attributes',{})
    endpoint=urlparse(a.get('action','')).path
    fields=[(f.get('name',''),f.get('type','text'),f.get('value','') if f.get('name')=='action' else '') for f in form.get('fields',[])]
    return {'method':a.get('method','get').lower(),'action_path':endpoint,'fields':fields}

def compare(runs,normalize_lt=False):
    pages=[];assets=collections.defaultdict(list);inline=collections.defaultdict(list);forms=collections.defaultdict(list);normalized=collections.defaultdict(list)
    for run in runs:
        fp=run/'fingerprints.json'
        data=json.loads(fp.read_text(encoding='utf-8-sig')) if fp.exists() else [json.loads(p.read_text(encoding='utf-8')) for p in run.glob('evidence/sites/*/fingerprint.json')]
        for page in data:
            pages.append({'run':str(run),'url':page['url'],'domain':page['domain'],'status':page.get('status'),'error':page.get('error'),'title':page.get('title'),'markers':page.get('markers',{}),'headings':page.get('headings',[])})
            if page.get('status')!=200:continue
            if normalize_lt:
                html_path=run/Path(page['directory'].replace('\\','/'))/'page.html'
                raw=html_path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=page['html_sha256']:raise ValueError('Saved HTML hash mismatch: '+str(html_path))
                parser=Page();parser.feed(raw.decode('utf-8','replace'))
                for s in parser.inline:
                    source=s['text']
                    norm,n=re.subn(r'var __lt="[^"\n]+";', 'var __lt="<REQUEST_TOKEN>";',source)
                    if n!=1:continue
                    key=re.search(r'__preludeSdkKey="([^"\n]+)"',source)
                    normalized[hashlib.sha256(norm.encode()).hexdigest()].append({'domain':page['domain'],'page':page['url'],'path':str(html_path),'raw_sha256':hashlib.sha256(source.encode()).hexdigest(),'characters':len(source),'normalization':'Replace exactly one var __lt quoted token; preserve all other bytes','public_sdk_key_sha256':hashlib.sha256(key.group(1).encode()).hexdigest() if key else None,'api_paths':sorted(set(re.findall(r'[\x22\x27](/api/[A-Za-z0-9/_?=-]+)[\x22\x27]',source)))})
            for a in page.get('assets',[]):
                if not a.get('sha256') or a.get('bytes',0)==0 or a.get('html_instead_of_asset'): continue
                path=run/Path(page['directory'].replace('\\','/'))/a['file']
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                if digest!=a['sha256']:raise ValueError('Saved file hash mismatch: '+str(path))
                assets[digest].append({'domain':page['domain'],'url':a['url'],'bytes':a['bytes'],'path':str(path),'standard_library':bool(LIBRARY.search(a['url']))})
            for s in page.get('inline_scripts',[]):
                if s['length']<100 or s['attributes'].get('type') in ('application/ld+json','speculationrules'):continue
                inline[s['sha256']].append({'domain':page['domain'],'page':page['url'],'characters':s['length']})
            for f in page.get('forms',[]):
                fs=form_sig(f)
                if len(fs['fields'])<3:continue
                forms[json.dumps(fs,sort_keys=True)].append({'domain':page['domain'],'page':page['url']})
    def groups(values,kind):
        out=[]
        for key,items in values.items():
            domains=sorted({x['domain'] for x in items})
            if len(domains)<2:continue
            unique=list({json.dumps(x,sort_keys=True):x for x in items}.values())
            out.append({'kind':kind,'signature':key,'domains':domains,'evidence':unique,'caution':'A reusable template/library can be shared by unrelated operators.'})
        return sorted(out,key=lambda x:(-len(x['domains']),x['signature']))
    return {'pages':pages,'shared_assets':groups(assets,'asset_sha256'),'shared_inline':groups(inline,'inline_sha256'),'shared_normalized_inline':groups(normalized,'normalized_inline_sha256'),'shared_forms':groups(forms,'form_structure'),'limitations':['No ownership inference is automatic.','Shared IP/NS and common libraries are discovery clues, not attribution.','Exact frontend code establishes reuse; inspect independent infrastructure, registration and campaign evidence.','Normalized matches are not exact raw-byte matches; each transformation is recorded.']}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs='+',type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--normalize-lt-token',action='store_true',help='Optional case-specific comparison: replace exactly one var __lt request token and record the transformation');a=p.parse_args()
    result=compare([x.resolve() for x in a.runs],a.normalize_lt_token);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pages':len(result['pages']),'asset_groups':len(result['shared_assets']),'inline_groups':len(result['shared_inline']),'normalized_groups':len(result['shared_normalized_inline']),'form_groups':len(result['shared_forms'])}))
