const {chromium}=require('/tmp/pw/node_modules/playwright-core');const fs=require('fs');
const D=__dirname;const M=JSON.parse(fs.readFileSync(D+'/manifest.json'));
(async()=>{const b=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
for(const m of M){const p=await b.newPage({viewport:{width:m.w,height:900},deviceScaleFactor:1});
await p.goto('file://'+D+'/'+m.html);await p.waitForTimeout(100);
const items=await p.evaluate(()=>{const out=[];const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
while(n=w.nextNode()){const t=n.textContent.trim();if(!t)continue;const el=n.parentElement;if(el.closest('style,script'))continue;
const cs=getComputedStyle(el);const r=document.createRange();r.selectNodeContents(n);
let op=1;for(let e=el;e;e=e.parentElement)op*=parseFloat(getComputedStyle(e).opacity);
let xf=false;for(let e=el;e&&e!==document.body;e=e.parentElement){if(getComputedStyle(e).transform!=='none')xf=true}
const c=el.closest('.cards');const cl=c?c.getBoundingClientRect():null;
out.push({xf,text:t,color:cs.color,size:parseFloat(cs.fontSize),weight:parseInt(cs.fontWeight),op,
rects:[...r.getClientRects()].map(q=>[q.left,q.top,q.right,q.bottom]),clip:cl?[cl.left,cl.top,cl.right,cl.bottom]:null,
role:(el.tagName.toLowerCase()+'.'+(typeof el.className==='string'?el.className.split(' ').join('.'):'')),
anc:[...(function*(){let e=el;while(e&&e!==document.body){if(typeof e.className==='string'&&e.className)yield e.className.split(' ')[0];e=e.parentElement}})()].slice(0,3).join('<')});}
return out});
await p.screenshot({path:`/tmp/cp/A_${m.png}`,fullPage:true});
await p.addStyleTag({content:'*{color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important}'});
await p.screenshot({path:`/tmp/cp/${m.png}`,fullPage:true});
fs.writeFileSync(`/tmp/cp/${m.png}.json`,JSON.stringify({theme:m.theme,name:m.name,items}));
await p.close()}
await b.close()})()
