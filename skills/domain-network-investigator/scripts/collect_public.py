"""Read-only public-site fingerprint collector. Never submits forms or executes JS.

Usage: python collect_public.py candidates.json --out new-run --assets 8 --metadata
Input: JSON list of public URLs. Output: timestamped evidence chosen by caller.
Only linked same-origin assets are downloaded; public library matches are weak.
"""
import argparse, concurrent.futures, datetime, hashlib, html, ipaddress, json, re, socket, sys, threading, time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = OUT = ARGS = None
RDAP_LOCK = threading.Lock()
RDAP_LIMITED = threading.Event()
RDAP_NEXT = 0.0
LIBRARY = re.compile(r'jquery|bootstrap|swiper|uikit|intlTelInput|normalize(?:\.min)?\.css|fbevents|cloudflare-static/(?:email-decode|rocket-loader)',re.I)

def public_url(url):
    u = urlparse(url)
    if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password or u.port not in (None,80,443):
        raise ValueError('Only public web URLs allowed')
    for entry in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == 'https' else 80)):
        if not ipaddress.ip_address(entry[4][0]).is_global:
            raise ValueError('Non-public address blocked')
    return url

class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def get(url):
    public_url(url)
    req = Request(url, headers={'User-Agent': 'PublicSiteComparison/1.0 (read-only research)', 'Accept': '*/*'})
    with build_opener(PublicRedirect()).open(req, timeout=ARGS.timeout if ARGS else 20) as r:
        b = r.read(3_000_001)
        if len(b) > 3_000_000:
            raise ValueError('Response larger than 3 MB')
        return b, dict(r.headers), r.geturl(), r.status

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets=[]; self.forms=[]; self.links=[]; self.tags=[]; self.text=[]; self.inline=[]
        self.form=None; self.script=None; self.skip=0; self.title=False; self.title_text=''; self.base_href=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); self.tags.append(tag)
        if tag=='base' and self.base_href is None and 'href' in a: self.base_href=a['href']
        if tag=='form':
            self.form={'attributes':a, 'fields':[]}; self.forms.append(self.form)
        if tag in ('input','select','textarea') and self.form is not None:
            # Dynamic visitor data and nonce values are not attribution indicators.
            if a.get('name','').lower() in ('ip','nonce','_wp_http_referer','clickid','click_id'):
                a.pop('value', None)
            self.form['fields'].append(a)
        if tag=='script':
            if a.get('src'): self.assets.append({'kind':'js','url':a['src'],'id':a.get('id')})
            self.script={'attributes':a,'text':''}; self.inline.append(self.script); self.skip+=1
        if tag=='style': self.skip+=1
        if tag=='link' and a.get('href') and ('stylesheet' in a.get('rel','') or 'icon' in a.get('rel','')):
            self.assets.append({'kind':'css' if 'stylesheet' in a.get('rel','') else 'icon','url':a['href'],'id':a.get('id')})
        if tag=='a' and a.get('href'): self.links.append(a['href'])
        if tag=='title': self.title=True
    def handle_endtag(self,tag):
        if tag=='form': self.form=None
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag=='script': self.script=None
        if tag=='title': self.title=False
    def handle_data(self,data):
        if self.script is not None: self.script['text']+=data
        if not self.skip and data.strip(): self.text.append(data.strip())
        if self.title: self.title_text+=data

def sha(b): return hashlib.sha256(b).hexdigest()

def scan(url):
    host=urlparse(url).hostname
    key=host+'_'+sha(url.encode())[:16]
    folder=OUT/key; folder.mkdir(exist_ok=True)
    result={'url':url,'domain':host,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'directory':folder.relative_to(ROOT).as_posix()}
    try:
        b,h,final,status=get(url); s=b.decode('utf-8','replace')
        (folder/'page.html').write_bytes(b)
        (folder/'headers.json').write_text(json.dumps(h,indent=2),encoding='utf-8')
        p=Page(); p.feed(s)
        effective_base=urljoin(final,p.base_href) if p.base_href is not None else final
        for f in p.forms:
            action=f['attributes'].get('action')
            f['resolved_action']=urljoin(effective_base,action) if action else final
        result.update(status=status, final_url=final, content_type=h.get('Content-Type'),base_href=p.base_href,effective_base=effective_base,html_sha256=sha(b),title=p.title_text,forms=p.forms,links=sorted(set(urljoin(effective_base,x) for x in p.links)),tags_sha256=sha(' '.join(p.tags).encode()),tags=p.tags)
        (folder/'text.txt').write_text('\n'.join(p.text),encoding='utf-8')
        result['markers']={x: x in s for x in getattr(ARGS,'marker',[])}
        result['text_path']=(folder/'text.txt').relative_to(ROOT).as_posix()
        result['headings']=re.findall(r'<h[12]\b[^>]*>(.*?)</h[12]>',s,re.I|re.S)
        result['headings']=[html.unescape(re.sub('<[^>]*>',' ',v)).strip() for v in result['headings']]
        result['inline_scripts']=[{'attributes':v['attributes'],'sha256':sha(v['text'].encode()),'length':len(v['text'])} for v in p.inline if v['text'].strip()]
        result['tracking_ids']=sorted(set(re.findall(r'\b(?:GTM-[A-Z0-9]+|G-[A-Z0-9]{6,}|UA-\d+-\d+)\b',s)))
        result['assets']=[]; count=0
        for a in sorted(p.assets, key=lambda a: {'js':0,'css':1,'icon':2}[a['kind']]):
            au=urljoin(effective_base,html.unescape(a['url'])); ar=dict(a,url=au)
            path=urlparse(au).path
            ar['standard_library']=bool(LIBRARY.search(path))
            custom=a['kind'] in ('js','css') and not ar['standard_library']
            if urlparse(au).netloc==urlparse(final).netloc and custom and count<ARGS.assets:
                count+=1
                try:
                    time.sleep(.15)
                    ab,ah,af,ast=get(au)
                    filename=f'asset_{count:02d}_'+re.sub('[^A-Za-z0-9._-]','_',Path(path).name)
                    (folder/filename).write_bytes(ab)
                    is_html=bool(re.search(br'<(?:!doctype\s+html|html)\b',ab[:2000],re.I))
                    ar.update(sha256=sha(ab),bytes=len(ab),file=filename,status=ast,content_type=ah.get('Content-Type'),final_url=af,html_instead_of_asset=is_html)
                except Exception as e: ar['error']=str(e)
            result['assets'].append(ar)
    except Exception as e:
        result['error']=str(e)
        if hasattr(e,'code'): result['http_error_status']=e.code
    (folder/'fingerprint.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('domain','url','status','title','error') if k in result},ensure_ascii=True),flush=True)
    return result

def metadata(domain):
    global RDAP_NEXT
    record={'domain':domain,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'dns':{}}
    for typ in ('A','NS'):
        try:
            url='https://dns.google/resolve?name='+domain+'&type='+typ
            b,_,_,_=get(url); record['dns'][typ]=json.loads(b)
        except Exception as e: record['dns'][typ]={'error':str(e)}
    with RDAP_LOCK:
        if RDAP_LIMITED.is_set():
            record['rdap_error']='Skipped after RDAP HTTP 403/429 earlier in this run'
        else:
            time.sleep(max(0,RDAP_NEXT-time.monotonic()))
            try:
                b,_,final,_=get('https://rdap.org/domain/'+domain)
                data=json.loads(b);record['rdap_url']=final;record['events']=data.get('events',[])
                (ROOT/'metadata'/('rdap-'+domain+'.json')).write_bytes(b)
            except Exception as e:
                record['rdap_error']=str(e)
                if getattr(e,'code',None) in (403,429):RDAP_LIMITED.set()
            finally:RDAP_NEXT=time.monotonic()+1
    return record

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--assets',type=int,default=8)
    parser.add_argument('--workers',type=int,choices=range(1,5),default=3)
    parser.add_argument('--timeout',type=int,default=20)
    parser.add_argument('--metadata',action='store_true',help='Fetch public DNS A/NS and registry RDAP once per domain')
    parser.add_argument('--marker',action='append',default=[],help='Literal observed in the active profile; repeatable, no inherited defaults')
    ARGS=parser.parse_args()
    if not 0<=ARGS.assets<=20: parser.error('--assets must be 0..20')
    ROOT=ARGS.out.resolve()
    if ROOT.exists() and any(ROOT.iterdir()): parser.error('--out must be a new or empty directory; preserve prior evidence')
    urls=json.loads(ARGS.input.read_text(encoding='utf-8-sig'))
    if not isinstance(urls,list) or not all(isinstance(u,str) for u in urls): parser.error('Input must be a JSON array of URLs')
    if len(urls)>250: parser.error('Use bounded batches of at most 250 URLs')
    if ARGS.timeout<1 or ARGS.timeout>60: parser.error('--timeout must be 1..60 seconds')
    for url in urls:
        parsed=urlparse(url)
        try:
            valid=parsed.scheme in ('http','https') and parsed.hostname and not parsed.username and not parsed.password and parsed.port in (None,80,443)
        except ValueError:
            valid=False
        if not valid: parser.error('Invalid public HTTP(S) URL: '+url)
    OUT=ROOT/'evidence'/'sites';OUT.mkdir(parents=True,exist_ok=True)
    (ROOT/'input.json').write_text(json.dumps(urls,indent=2),encoding='utf-8')
    with concurrent.futures.ThreadPoolExecutor(max_workers=ARGS.workers) as pool:
        results=list(pool.map(scan, dict.fromkeys(urls)))
    (ROOT/'fingerprints.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    if ARGS.metadata:
        (ROOT/'metadata').mkdir(exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=ARGS.workers) as pool:
            meta=list(pool.map(metadata,sorted({urlparse(u).hostname for u in urls})))
        (ROOT/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pages':len(results),'ok':sum(x.get('status')==200 for x in results),'out':str(ROOT)},ensure_ascii=True))
