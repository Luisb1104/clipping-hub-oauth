import json,statistics as st
from playwright.sync_api import sync_playwright
U="file:///workspace/shared-kit/demo.html"
JS="""()=>new Promise(r=>{let cls=0,lt=0,ltn=0;
new PerformanceObserver(l=>{}).observe({type:'layout-shift',buffered:true});
const n=performance.getEntriesByType('navigation')[0];
let fcp=null;new PerformanceObserver(l=>{for(const e of l.getEntries())if(e.name=='first-contentful-paint')fcp=e.startTime}).observe({type:'paint',buffered:true});
setTimeout(()=>{ // let animations finish (~1s), then read buffered entries
 const po=new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)cls+=e.value});
 po.observe({type:'layout-shift',buffered:true});
 const pl=new PerformanceObserver(l=>{for(const e of l.getEntries()){lt+=e.duration;ltn++}});
 try{pl.observe({type:'longtask',buffered:true})}catch(e){}
 setTimeout(()=>r({paints:JSON.stringify(performance.getEntriesByType('paint')),fcp,dcl:n.domContentLoadedEventEnd,load:n.loadEventEnd,cls,longtasks:ltn,num:document.querySelector('[data-count]').textContent,anim:document.getAnimations().length}),100)},1200)})"""
def run(q,rm=False):
    out=[]
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path="/usr/bin/google-chrome",headless=True,args=["--no-sandbox"])
        for i in range(7):
            c=b.new_context(viewport={"width":1000,"height":700},reduced_motion="reduce" if rm else "no-preference")
            pg=c.new_page();pg.goto(U+q);out.append(pg.evaluate(JS));c.close()
        b.close()
    return out
res={}
for name,q,rm in [("kit_off","?kit=0",False),("kit_on","",False),("kit_on_reduced_motion","",True)]:
    o=run(q,rm)
    res[name]={k:(st.median([x[k] for x in o])) for k in("fcp","dcl","load","cls","longtasks","anim")}
    res[name]["final_text"]=sorted({x["num"] for x in o})
    res[name]["fcp_runs"]=[round(x["fcp"],1) for x in o]
print(json.dumps(res,indent=1));json.dump(res,open("bench-results.json","w"),indent=1)

# count-up sanity: re-arm the number and sample textContent while it animates
def sample():
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path="/usr/bin/google-chrome",headless=True,args=["--no-sandbox"])
        pg=b.new_page();pg.goto(U);pg.wait_for_timeout(700)
        pg.evaluate("()=>{var e=document.querySelector('[data-count]');delete e.dataset.mDone;window.S=[];var i=setInterval(function(){S.push(e.textContent)},50);setTimeout(function(){clearInterval(i)},800);mCount()}")
        pg.wait_for_timeout(1000)
        print("countup samples:"," | ".join(pg.evaluate("S")))
        print("draw dasharray after:",pg.evaluate("getComputedStyle(document.querySelector('.m-draw')).strokeDasharray"))
        b.close()
sample()
