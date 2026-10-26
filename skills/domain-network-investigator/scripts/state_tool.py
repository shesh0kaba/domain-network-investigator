"""Validate isolated team profiles and triage novelty; never auto-attribute sites.

Usage: state_tool.py validate investigation-state
       state_tool.py triage investigation-state candidates.json --profile team-001 --out triage.json
"""
import argparse,json,re,unicodedata
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def brand_key(value):return ' '.join(unicodedata.normalize('NFKC',value).casefold().split())
def host(value):
    u=urlsplit(value if '://' in value else 'https://'+value)
    if not u.hostname or u.username or u.password:raise ValueError('Invalid domain or URL: '+value)
    return u.hostname.rstrip('.').encode('idna').decode().lower()
def url_key(value):
    u=urlsplit(value)
    if u.scheme.lower() not in ('https','http'):raise ValueError('Expected HTTP(S) URL: '+value)
    h=host(value);port=u.port
    if ':' in h:h='['+h+']'
    netloc=h+((':'+str(port)) if port and not (u.scheme.lower()=='https' and port==443 or u.scheme.lower()=='http' and port==80) else '')
    return urlunsplit((u.scheme.lower(),netloc,u.path or '/',u.query,''))

def validate(root):
    root=root.resolve();r=read(root/'registry.json')
    if r.get('schema_version')!=1:raise ValueError('Unsupported schema version')
    profiles={};pattern_ids=set()
    for entry in r['profiles']:
        pid=entry['id']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*',pid) or pid in profiles:raise ValueError('Duplicate/invalid profile ID')
        path=(root/entry['path']).resolve()
        if not path.is_relative_to(root):raise ValueError('Profile path escapes state directory')
        p=read(path)
        if p['id']!=pid or p['name']!=entry['name'] or p['kind']!='user_team_profile':raise ValueError('Profile identity mismatch')
        for key in ('identity_status','user_seeds','patterns','assessments','source_refs'):
            if key not in p:raise ValueError('Missing profile field: '+key)
        for pat in p['patterns']:
            if pat['id'] in pattern_ids:raise ValueError('Duplicate pattern ID')
            pattern_ids.add(pat['id'])
            if pat['profile_id']!=pid:raise ValueError('Cross-profile pattern contamination: '+pat['id'])
            if pat['scope'] not in ('team_hypothesis','campaign_family','shared_platform','generic'):raise ValueError('Unknown pattern scope')
            if pat['use'] not in ('discovery_only','corroboration','specific_evidence'):raise ValueError('Unknown pattern use')
            if pat['scope'] in ('shared_platform','generic') and pat['use']!='discovery_only':raise ValueError('Shared technology cannot become team-specific evidence automatically')
            if not pat.get('source_refs'):raise ValueError('Pattern needs source references')
        profiles[pid]=p
    if r.get('active_profile_id') not in profiles:raise ValueError('Active profile is missing')
    seen=set()
    for d in r['domains']:
        key=host(d['domain'])
        if key in seen:raise ValueError('Duplicate domain: '+key)
        seen.add(key)
        if set(d['seen_in_profiles'])-profiles.keys():raise ValueError('Unknown profile on domain')
        for u in d['urls']:
            if host(u)!=key:raise ValueError('URL belongs to a different domain: '+u)
    brand_ids=set()
    for b in r['brands']:
        if b['id'] in brand_ids:raise ValueError('Duplicate brand ID')
        brand_ids.add(b['id'])
        if b['seo']['status'] not in ('not_checked','not_found_in_checks','domain_candidate','site_found','google_result_verified','previously_seen_unavailable'):raise ValueError('Invalid SEO discovery state')
        for a in b['profile_assessments']:
            if a['profile_id'] not in profiles:raise ValueError('Unknown profile on brand')
    frontier=read(root/'frontier.json')
    for item in frontier['items']:
        if item['profile_id'] not in profiles:raise ValueError('Unknown profile on frontier')
    return r,profiles

def triage(root,candidates,profile):
    r,profiles=validate(root)
    if profile not in profiles:raise ValueError('Choose an existing profile after the grouping decision')
    if not isinstance(candidates,list) or any(not isinstance(x,dict) for x in candidates):raise ValueError('Candidate input must be an array of objects')
    known={host(d['domain']):d for d in r['domains']}
    names={brand_key(n) for b in r['brands'] for n in [b['name']]+b.get('aliases',[])}
    out=[];seen=set()
    for c in candidates:
        h=host(c.get('url') or c['domain']);u=url_key(c['url']) if c.get('url') else None
        if c.get('domain') and host(c['domain'])!=h:raise ValueError('Candidate domain/URL mismatch')
        b=brand_key(c['brand']) if c.get('brand') else None;k=(h,u,b)
        if k in seen:continue
        seen.add(k);d=known.get(h)
        out.append({'candidate':c,'domain':h,'selected_profile_id':profile,'domain_novelty':'known' if d else 'new','url_novelty':('known' if d and u in {url_key(x) for x in d['urls']} else 'new') if u else 'not_provided','profile_novelty':'known_lead' if d and profile in d['seen_in_profiles'] else 'new_lead','brand_novelty':('known' if b in names else 'new') if b else 'not_provided','prior_discovery_only':bool(d and d.get('discovery_only')),'team_attribution':'not_assessed_by_this_tool'})
    return {'profile_id':profile,'profile_name':profiles[profile]['name'],'registry_modified':False,'candidates':out}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('validate');p.add_argument('state',type=Path)
    p=sub.add_parser('triage');p.add_argument('state',type=Path);p.add_argument('input',type=Path);p.add_argument('--profile',required=True);p.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    if a.command=='validate':
        r,profiles=validate(a.state);print(json.dumps({'valid':True,'profiles':len(profiles),'domains':len(r['domains']),'brands':len(r['brands']),'active_profile':r['active_profile_id']}))
    else:
        if a.out.resolve().is_relative_to(a.state.resolve()) or a.out.resolve()==a.input.resolve():parser.error('--out must be outside the state directory and must not replace the input')
        result=triage(a.state,read(a.input),a.profile);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'candidates':len(result['candidates']),'registry_modified':False}))
