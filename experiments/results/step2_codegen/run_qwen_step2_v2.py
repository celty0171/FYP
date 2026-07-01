import json, re, subprocess, sys, time, urllib.request
from pathlib import Path
EXP=Path("/rds/general/user/jm1125/home/FYP/experiments")
PROMPT=(EXP/"prompts"/"step2_chart_mapping_prompt_v2.md").read_text()
HERE=EXP/"results"/"step2_codegen"
SCHEMA=EXP/"mondial_database"/"mondial_schema_summary_clean.json"
CASES=HERE/"cases_with_pattern.json"
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
(HERE/"raw_qwen_step2_v2.txt").write_text(content)
cp=HERE/"qwen_recommend_charts_v2.py"; cp.write_text(code)
op=HERE/"recommendations_qwen_v2.json"
p=subprocess.run([sys.executable,str(cp),"--schema",str(SCHEMA),"--cases",str(CASES),"--out",str(op)],capture_output=True,text=True)
if p.returncode!=0:
    print("RUN FAILED:\n",p.stderr[:1800]); sys.exit()
Q={r['case_id']:r for r in json.loads(op.read_text())['results']}
Rref={r['case_id']:r for r in json.loads((HERE/'recommendations.json').read_text())['results']}
print("=== Qwen Step-2 vs reference ===")
sel_match=0; rec_match=0
for cid in sorted(Q,key=int):
    q=Q[cid]; ref=Rref[cid]
    qsel=q.get('selected',{}); rsel=ref.get('selected',{})
    sm = qsel.get('chart')==rsel.get('chart') and qsel.get('mapping')==rsel.get('mapping')
    rm = set(q.get('recommended_charts',[]))==set(ref.get('recommended_charts',[]))
    sel_match+=sm; rec_match+=rm
    print(f"case {cid} {ref['identified_pattern']:28s} selected:{'OK' if sm else 'DIFF'} recommended:{'OK' if rm else 'DIFF'}")
    if not sm: print(f"    qwen sel: {qsel.get('chart')} {qsel.get('mapping')}")
    if not rm: print(f"    qwen rec: {q.get('recommended_charts')}  ref: {ref.get('recommended_charts')}")
print(f"\nselected mapping match: {sel_match}/9 | recommended-set match: {rec_match}/9")
