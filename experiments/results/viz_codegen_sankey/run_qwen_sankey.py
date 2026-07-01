import json, re, subprocess, sys, time, urllib.request
from pathlib import Path
EXP=Path("/rds/general/user/jm1125/home/FYP/experiments")
PROMPT=(EXP/"prompts"/"viz_codegen_sankey_prompt.md").read_text()
HERE=EXP/"results"/"viz_codegen_sankey"
MAP=HERE/"mapping_encompasses.json"
DATA=EXP/"mondial_database"/"mondial_encompasses_data.json"
payload={"model":"Qwen3-14B","messages":[{"role":"user","content":PROMPT}],
         "temperature":0.0,"max_tokens":4096,"chat_template_kwargs":{"enable_thinking":False}}
req=urllib.request.Request("http://localhost:8001/v1/chat/completions",
    data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer dummy"},method="POST")
t0=time.time()
with urllib.request.urlopen(req,timeout=600) as r: resp=json.loads(r.read())
dt=time.time()-t0
ch=resp["choices"][0]; content=ch["message"].get("content") or ""
print(f"{dt:.0f}s finish={ch.get('finish_reason')} tokens={resp['usage'].get('completion_tokens')}")
text=re.sub(r"<think>.*?</think>","",content,flags=re.DOTALL).strip()
m=re.search(r"```(?:python)?\s*\n(.*?)```",text,flags=re.DOTALL)
code=(m.group(1).strip() if m else text)+"\n"
(HERE/"raw_qwen_sankey.txt").write_text(content)
cp=HERE/"qwen_render_sankey.py"; cp.write_text(code)
op=HERE/"encompasses_qwen.html"
p=subprocess.run([sys.executable,str(cp),"--mapping",str(MAP),"--data",str(DATA),"--out",str(op)],capture_output=True,text=True)
if p.returncode!=0:
    print("RUN FAILED:\n",p.stderr[:1500]); sys.exit()
h=op.read_text(); rows=json.load(open(DATA))
pairs={(r['country'],r['continent']) for r in rows}
nums=re.findall(r'"[A-Za-z]+"',h)  # rough
print("html bytes:", len(h))
print("complete (DOCTYPE..</html>):", h.strip().lower().startswith('<!doctype') and h.strip().lower().endswith('</html>'))
print("has <title>:", '<title>' in h.lower())
print("loader pinned:", 'gstatic.com/charts/loader.js' in h)
print("packages sankey:", "'sankey'" in h or '"sankey"' in h)
# count rows that appear: check all continents present and a sample of countries
conts={r['continent'] for r in rows}
print("all continents present:", all(c in h for c in conts), conts)
present=sum(1 for r in rows if r['country'] in h)
print(f"country codes present in html: ~{present}/{len(rows)} (rough substring)")
