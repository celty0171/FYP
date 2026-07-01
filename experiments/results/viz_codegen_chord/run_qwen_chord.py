import json, re, subprocess, sys, time, urllib.request
from pathlib import Path
EXP=Path("/rds/general/user/jm1125/home/FYP/experiments")
BASE=(EXP/"prompts"/"viz_codegen"/"base_d3v7.md").read_text()
CHART=(EXP/"prompts"/"viz_codegen"/"chart_chord.md").read_text()
PROMPT=BASE+"\n\n"+CHART
HERE=EXP/"results"/"viz_codegen_chord"
MAP=HERE/"mapping_borders.json"; DATA=EXP/"mondial_database"/"mondial_data.json"
payload={"model":"Qwen3-14B","messages":[{"role":"user","content":PROMPT}],
         "temperature":0.0,"max_tokens":6144,"repetition_penalty":1.1,
         "chat_template_kwargs":{"enable_thinking":False}}
req=urllib.request.Request("http://localhost:8001/v1/chat/completions",
    data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer dummy"},method="POST")
t0=time.time()
with urllib.request.urlopen(req,timeout=900) as r: resp=json.loads(r.read())
dt=time.time()-t0
ch=resp["choices"][0]; content=ch["message"].get("content") or ""
print(f"{dt:.0f}s finish={ch.get('finish_reason')} tokens={resp['usage'].get('completion_tokens')}")
text=re.sub(r"<think>.*?</think>","",content,flags=re.DOTALL).strip()
fence=re.search(r"```(?:python)?\s*\n(.*?)```",text,flags=re.DOTALL)
code=(fence.group(1).strip() if fence else re.sub(r"^```[\w+\-]*\s*\n","",text).rstrip("`").strip())+"\n"
(HERE/"raw_qwen_chord.txt").write_text(content)
cp=HERE/"qwen_render_chord.py"; cp.write_text(code)
op=HERE/"borders_qwen.html"
p=subprocess.run([sys.executable,str(cp),"--mapping",str(MAP),"--data",str(DATA),"--out",str(op)],capture_output=True,text=True)
if p.returncode!=0:
    print("RUN FAILED:\n",p.stderr[:1800]); sys.exit()
h=op.read_text(); rows=json.load(open(DATA))
names=sorted({str(r['country1']) for r in rows}|{str(r['country2']) for r in rows}); n=len(names)
script=h[h.lower().find('<script'):]
print("--- structural + JS sanity ---")
print("complete:", h.strip().lower().startswith('<!doctype') and h.strip().lower().endswith('</html>'), "| d3 v7:", 'd3js.org/d3.v7.min.js' in h, "| d3.chord:", 'd3.chord' in h)
print("python funcs in JS:", [x for x in ['html.unescape','html.escape(','json.dumps','Path('] if x in script] or "none")
m2=re.search(r'=\s*(\[\[[\s\S]*?\]\])\s*;',h)
print("2D matrix:", (lambda m: f"{len(m)}x{len(m[0])} square={len(m)==n}" if m else "NO")(json.loads(m2.group(1)) if m2 else None))
print(f"names present: ~{sum(1 for nm in names if re.compile(chr(34)+re.escape(nm)+chr(34)).search(h))}/{n}")
print("--- INTERACTION (new requirement) ---")
print("mouseover handlers:", len(re.findall(r'\.on\(\s*[\"\']mouseover',script)))
print("mousemove/out:", len(re.findall(r'\.on\(\s*[\"\']mousemove',script)), "/", len(re.findall(r'\.on\(\s*[\"\']mouseout',script)))
print("tooltip element:", bool(re.search(r'id=["\']tip|class=["\']tooltip|append\(["\']div',h)) or '.append("title")' in h or "append('title')" in h)
print("uses event.pageX:", 'pageX' in h, "| native <title> tooltip:", '.append("title")' in h or "append('title')" in h)
print("highlight/de-emphasise (opacity change in handler):", bool(re.search(r'(fill-opacity|opacity)["\']', script)) and 'mouseover' in script)
