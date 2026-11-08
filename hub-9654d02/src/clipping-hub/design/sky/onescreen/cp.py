import json,glob,os,re,sys
from PIL import Image
D=os.path.dirname(os.path.abspath(__file__))
def lum(c):
    f=lambda v:(v/255/12.92) if v/255<=.03928 else ((v/255+.055)/1.055)**2.4
    return .2126*f(c[0])+.7152*f(c[1])+.0722*f(c[2])
def cr(a,b):
    la,lb=lum(a),lum(b); hi,lo=max(la,lb),min(la,lb); return (hi+.05)/(lo+.05)
def parse(c):
    m=re.findall(r'[\d.]+',c); v=[float(x) for x in m]; return (v[0],v[1],v[2],v[3] if len(v)>3 else 1.0)
rows=[]
for f in sorted(glob.glob('/tmp/cp/clip-*.png')):
    im=Image.open(f).convert('RGB'); imA=Image.open(os.path.dirname(f)+'/A_'+os.path.basename(f)).convert('RGB'); pa=imA.load(); W,H=im.size; px=im.load(); d=json.load(open(f+'.json'))
    for it in d['items']:
        col=parse(it['color']); a=col[3]*it['op']
        worst=99.0; n=0
        for (l,t,r,b) in it['rects']:
            if it['clip']: l=max(l,it['clip'][0]);t=max(t,it['clip'][1]);r=min(r,it['clip'][2]);b=min(b,it['clip'][3])
            l,t,r,b=int(max(0,l)),int(max(0,t)),int(min(W-1,r)),int(min(H-1,b))
            if r<=l or b<=t: continue
            for y in range(t,b+1,2):
                for x in range(l,r+1,2):
                    p=px[x,y]
                    if it.get('xf') and max(abs(pa[x,y][i]-p[i]) for i in range(3))<10: continue
                    fg=tuple(col[i]*a+p[i]*(1-a) for i in range(3))
                    worst=min(worst,cr(fg,p)); n+=1
        if n==0: continue
        bold=it['weight']>=700
        large=it['size']>=24 or (it['size']>=18.66 and bold)
        need=3.0 if large else 4.5
        rows.append(dict(theme=d['theme'],screen=d['name'],text=it['text'][:70],size=it['size'],weight=it['weight'],ratio=round(worst,2),large=large,need=need,ok=worst>=need,role=it['role'],anc=it['anc'],color=it['color']))
json.dump(rows,open(D+'/contrast_pairs.json','w'),indent=0)
bad=[r for r in rows if not r['ok']]
print(len(rows),'text pairs;',len(bad),'below threshold; min font',min(r['size'] for r in rows))
for r in sorted(bad,key=lambda r:r['ratio'])[:40]: print(r['ratio'],r['need'],r['theme'],r['screen'],repr(r['text']),r['size'],r['anc'])
