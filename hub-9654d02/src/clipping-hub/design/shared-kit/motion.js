/* motion.js: optional one-shot count-up. <b data-count="1234.5">1,234.5</b>; no JS = number just shows. mCount(root) for late nodes. */
(function(d,w){var R=w.matchMedia&&matchMedia("(prefers-reduced-motion:reduce)").matches;
function go(e){var s=e.dataset.count,t=parseFloat(s),o=e.textContent,f=(s.split(".")[1]||"").length,n,a;
if(R||!isFinite(t)||e.dataset.mDone||!/\d/.test(o))return;e.dataset.mDone=1;
e.style.display="inline-block";e.style.minWidth=e.offsetWidth+"px";
function k(x){a=a||x;n=Math.min((x-a)/500,1);
e.textContent=n<1?o.replace(/[\d,]*\.?\d+/,(t*(1-Math.pow(1-n,3))).toLocaleString("en-US",{minimumFractionDigits:f,maximumFractionDigits:f})):o;
if(n<1)requestAnimationFrame(k)}requestAnimationFrame(k)}
w.mCount=function(r){(r||d).querySelectorAll("[data-count]").forEach(go)};
d.readyState=="loading"?d.addEventListener("DOMContentLoaded",function(){mCount()}):mCount()})(document,window);
