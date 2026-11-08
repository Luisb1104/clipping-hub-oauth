const {chromium}=require('/tmp/pw/node_modules/playwright-core');const fs=require('fs');
const D=__dirname;const M=JSON.parse(fs.readFileSync(D+'/manifest.json'));const meas={};
(async()=>{const b=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
for(const m of M){const p=await b.newPage({viewport:{width:m.w,height:900},deviceScaleFactor:m.dpr});
await p.goto('file://'+D+'/'+m.html);await p.waitForTimeout(150);
const r=await p.evaluate(()=>{const f=document.querySelector('.phone,.mac');const inn=f.querySelector('.in');const fr=f.getBoundingClientRect();
const nav=f.querySelector('.navC');const navTop=nav?nav.getBoundingClientRect().top-fr.top:fr.height;
let cb=0;inn.querySelectorAll('*').forEach(e=>{if(e.closest('.cards'))return;const r=e.getBoundingClientRect();if(r.height>0)cb=Math.max(cb,r.bottom-fr.top)});
let cr=0;inn.querySelectorAll('*').forEach(e=>{if(e.closest('.cards'))return;const r=e.getBoundingClientRect();if(r.width>0)cr=Math.max(cr,r.right-fr.left)});
let ov=[];const w=document.createTreeWalker(f,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode()){const t=n.textContent.trim();if(!t)continue;const el=n.parentElement;if(el.closest('.cards'))continue;const box=el.closest('.chip,.btn,.pstrip div,.seg div,.navC a,.pl,.tg i,.th,.tabsM a');if(!box)continue;const rg=document.createRange();rg.selectNodeContents(n);const rr=rg.getBoundingClientRect(),bb=box.getBoundingClientRect();if(rr.right>bb.right+0.5||rr.left<bb.left-0.5||rr.bottom>bb.bottom+0.5||rr.top<bb.top-0.5)ov.push(t)}
return {textOverflow:ov,frameW:fr.width,frameH:fr.height,innerScrollH:inn.scrollHeight,innerClientH:inn.clientHeight,innerScrollW:inn.scrollWidth,innerClientW:inn.clientWidth,contentBottom:Math.round(cb),navTop:Math.round(navTop),contentRight:Math.round(cr),pageH:document.documentElement.scrollHeight}});
const ok=r.textOverflow.length===0&&r.innerScrollH<=r.frameH&&r.innerScrollW<=r.innerClientW&&r.contentBottom<=r.navTop-2&&r.contentRight<=r.frameW;
meas[m.png]={...r,ok};console.log(ok?'OK ':'BAD',m.png,JSON.stringify(r));
await p.screenshot({path:D+'/'+m.png,fullPage:true});await p.close()}
fs.writeFileSync(D+'/measurements.json',JSON.stringify(meas,null,1));await b.close()})()
