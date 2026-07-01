import json, re, subprocess, sys, time, urllib.request
from pathlib import Path
EXP=Path("/rds/general/user/jm1125/home/FYP/experiments")
BASE=(EXP/"prompts"/"viz_codegen"/"base_d3v7.md").read_text()
CHART=(EXP/"prompts"/"viz_codegen"/"chart_chord.md").read_text()
PROMPT=BASE+"\n\n"+CHART
HERE=EXP/"results"/"viz_codegen_chord"
MAP=HERE/"mapping_borders.json"; DATA=EXP/"mondial_database"/"mondial_data.json"
def run(i):
    payload={"model":"Qwen3-14B","messages":[{"role":"user","content":PROMPT}],
             "temperature":0.0,"max_tokens":6144,"repetition_penalty":1.1,
             "chat_template_kwargs":{"enable_thinking":False}}
    req=urllib.request.Request("http://localhost:8001/v1/chat/completions",
        data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer dummy"},method="POST")
    t0=time.time()
    with urllib.request.urlopen(req,timeout=900) as r: resp=json.loads(r.read())
    dt=time.time()-t0
    content=resp["choices"][0]["message"].get("content") or ""
    text=re.sub(r"<think>.*?</think>","",content,flags=re.DOTALL).strip()
    fence=re.search(r"```(?:python)?\s*\n(.*?)```",text,flags=re.DOTALL)
    code=(fence.group(1).strip() if fence else re.sub(r"^```[\w+\-]*\s*\n","",text).rstrip("`").strip())+"\n"
    cp=HERE/f"qwen_unguarded_{i}.py"; cp.write_text(code)
    # how did it build the HTML?
    method=[]
    if re.search(r'=\s*f"""|=\s*f\'\'\'|return\s+f"""',code): method.append("f-string")
    if ".format(" in code: method.append(".format()")
    if re.search(r'"""\s*\+|\+\s*"""|\.replace\("__',code): method.append("concat/replace")
    op=HERE/f"borders_unguarded_{i}.html"
    p=subprocess.run([sys.executable,str(cp),"--mapping",str(MAP),"--data",str(DATA),"--out",str(op)],capture_output=True,text=True)
    ok=p.returncode==0
    err=("" if ok else (p.stderr.strip().splitlines()[-1] if p.stderr.strip() else ""))
    print(f"run {i}: {dt:.0f}s  build={method or ['?']}  RUNS={ok}  {('' if ok else '-> '+err[:90])}")
    return ok
results=[run(i) for i in range(1,4)]
print(f"\nun-guarded feasibility: {sum(results)}/3 runs produced a runnable renderer")
