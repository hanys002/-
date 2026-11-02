"""정적 검색 페이지 생성 (GitHub Pages / Actions 아티팩트 / 로컬 열람용)."""
from __future__ import annotations

import json
from pathlib import Path

from .ingest import INDEX

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>삼성노트 검색</title>
<style>
:root{--bg:#f7f8fa;--fg:#1d2330;--mut:#5f6b7a;--card:#fff;--line:#dde2e8;--acc:#1259c3;--hl:#ffe58a}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--fg:#e6e9ee;--mut:#9aa5b4;--card:#1b2029;--line:#2c3340;--acc:#7db0ff;--hl:#6b5a12}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,"Noto Sans KR","Apple SD Gothic Neo",sans-serif}
main{max-width:860px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:20px;margin:0 0 4px}.meta{color:var(--mut);font-size:13px}
input{width:100%;padding:12px 14px;font-size:16px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--fg);margin:14px 0 6px}
.hint{color:var(--mut);font-size:12px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.card h2{font-size:16px;margin:0 0 4px;cursor:pointer;color:var(--acc)}
.card .s{color:var(--mut);font-size:12px}.card p{margin:6px 0 0;word-break:break-all}
mark{background:var(--hl);color:inherit;padding:0 1px;border-radius:2px}
pre{white-space:pre-wrap;word-break:break-all;font-family:inherit;font-size:14px;line-height:1.6;margin:8px 0 0;display:none}
.open pre{display:block}.badge{font-size:11px;border:1px solid var(--line);border-radius:6px;padding:0 5px;margin-left:6px}
</style></head><body><main>
<h1>삼성노트 검색</h1><div class="meta" id="meta">색인 불러오는 중…</div>
<input id="q" type="search" placeholder="검색어 (예: 계측제어 &quot;5G 특화망&quot; -초안 tag:회의)" autofocus>
<div class="hint">공백=AND · "구절" · -제외 · tag:태그 · 결과 제목을 누르면 전문 표시</div>
<div id="out"></div></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const norm=s=>(s||"").normalize("NFKC").toLowerCase().replace(/\s+/g," ");
const JOSA=["에서는","으로는","에게서","이라고","에서","에게","으로","까지","부터","처럼","보다","이나","은","는","이","가","을","를","에","의","와","과","로","도","만","나"];
const unJosa=t=>{for(const j of JOSA)if(t.endsWith(j)&&t.length-j.length>=2)return t.slice(0,-j.length);return t};
const ns=s=>s.replace(/ /g,"");
function parse(q){const ph=[...q.matchAll(/"([^"]+)"/g)].map(m=>norm(m[1]));const r=q.replace(/"[^"]*"/g," ").split(/\s+/).filter(Boolean);const inc=[],exc=[],tags=[];for(const t of r){if(t.startsWith("-")&&t.length>1)exc.push(norm(t.slice(1)));else if(/^tag:/i.test(t)&&t.length>4)tags.push(norm(t.slice(4)));else inc.push(norm(t))}return{must:[...inc,...ph],exc,tags}}
function search(docs,q){const Q=parse(q);const hits=[];for(const d of docs){const title=norm(d.title),hay=title+" "+norm(d.text);const tg=(d.tags||[]).map(norm);if(Q.tags.some(t=>!tg.includes(t)))continue;if(Q.exc.some(e=>hay.includes(e)))continue;let sc=0,ok=true;for(const t of Q.must){if(hay.includes(t)){sc+=10+5*title.includes(t)+Math.min(hay.split(t).length-1,10)}else{const h=d._ns||(d._ns=ns(hay));if(h.includes(ns(t))||h.includes(ns(unJosa(t)))){sc+=6;continue}ok=false;break}}if(!ok||(!Q.must.length&&!Q.tags.length))continue;hits.push({d,sc})}hits.sort((a,b)=>b.sc-a.sc||(a.d.modified<b.d.modified?1:a.d.modified>b.d.modified?-1:0));Q.hl=[...new Set(Q.must.flatMap(t=>[t,unJosa(t)]))];return{hits,Q}}
const esc=s=>s.replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function hl(text,terms){let h=esc(text);for(const t of terms.filter(Boolean).sort((a,b)=>b.length-a.length)){const re=new RegExp(esc(t).replace(/[.*+?^${}()|[\]\\]/g,"\\$&"),"gi");h=h.replace(re,m=>"<mark>"+m+"</mark>")}return h}
function snip(text,terms){const flat=text.replace(/\s+/g," "),low=norm(flat);for(const t of terms){const i=low.indexOf(t);if(i>=0){const a=Math.max(0,i-60),b=Math.min(flat.length,i+t.length+60);return(a?"…":"")+flat.slice(a,b)+(b<flat.length?"…":"")}}return flat.slice(0,120)}
let DOCS=[];
function render(){const q=document.getElementById("q").value.trim();const out=document.getElementById("out");try{localStorage.setItem("snq",q)}catch(e){}
 const list=q?search(DOCS,q):{hits:DOCS.slice(0,30).map(d=>({d,sc:0})),Q:{must:[],hl:[]}};
 out.innerHTML=(q?`<div class="meta">${list.hits.length}건</div>`:`<div class="meta">최근 노트</div>`)+list.hits.slice(0,100).map(({d})=>`<div class="card"><h2 onclick="this.parentNode.classList.toggle('open')">${esc(d.title)}${d.quality!=="exact"?`<span class="badge">${d.quality==="ocr"?"OCR":"추정"}</span>`:""}</h2><div class="s">${esc(d.modified.slice(0,10))} · ${esc(d.source)}${(d.tags||[]).map(t=>" #"+esc(t)).join("")}</div><p>${hl(snip(d.text,list.Q.hl),list.Q.hl)}</p><pre>${hl(d.text,list.Q.hl)}</pre></div>`).join("")}
const inline=document.getElementById("data");
(inline&&inline.textContent.trim()?Promise.resolve(JSON.parse(inline.textContent)):fetch("index.json").then(r=>r.json())).then(j=>{DOCS=j.notes;document.getElementById("meta").textContent=`노트 ${j.count}개 · 색인 ${j.generated.replace("T"," ").slice(0,16)} UTC`;
 try{const s=localStorage.getItem("snq");if(s)document.getElementById("q").value=s}catch(e){}render()}).catch(e=>{document.getElementById("meta").textContent="index.json 을 불러오지 못했습니다: "+e});
document.getElementById("q").addEventListener("input",render);
</script>
</body></html>
"""


def build_site(out_dir: Path) -> Path:
    """색인을 페이지 안에 내장 → 파일을 바로 열어도(file://) 동작한다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    data = INDEX.read_text(encoding="utf-8").strip() if INDEX.exists() else json.dumps(
        {"generated": "", "count": 0, "notes": []})
    # </script> 조기 종료 방지
    data = data.replace("</", "<\\/")
    out = out_dir / "index.html"
    out.write_text(PAGE.replace("__DATA__", data), encoding="utf-8")
    return out
