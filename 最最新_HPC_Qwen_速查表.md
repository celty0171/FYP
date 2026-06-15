# HPC 上 Qwen 部署 · 完整操作手册

> 集群: Imperial cx3 | 登录节点: `login-b.cx3.hpc.ic.ac.uk` | 用户: `jm1125`
> 模型目录: `~/models/` | conda 环境: `qwen3`

> **SSH 别名**: 已在 WSL `~/.ssh/config` 配好 `hpc` = `login-b.cx3.hpc.ic.ac.uk`
> 所以 `ssh hpc` 即可连 HPC,隧道里也用 `-J hpc` 代替长地址。
> **务必用 `login-b`**(有 qsub);`login-ai` 等其他登录节点没有 qsub。

> **队列: 不要写 `#PBS -q`**。cx3 用路由队列,PBS 按你申请的资源自动选 GPU 队列
> (gpu72 / gpu72_8),哪个能先跑进哪个。写死队列反而可能拖慢排队(官方建议)。
> **gpu_type**: 大模型(14B/32B/Coder/AWQ)保留 `gpu_type=L40S`(要大显存);
> 小模型(8B/7B)去掉 gpu_type,任意卡都行,排队更快。

---

## 模型总表(8 个 · 端口全错开,可同时跑)

| 模型 | 脚本 | 卡 | 端口 | 调用时的 model 名 | 用途 |
|------|------|----|----|------|------|
| Qwen3-14B | `serve_qwen.pbs` | 1 | 8001 | `Qwen3-14B` | 通用·均衡 |
| Qwen3-8B | `serve_qwen8b.pbs` | 1 | 8002 | `Qwen3-8B` | 通用·轻快 |
| Qwen3-32B | `serve_qwen32b.pbs` | 2 | 8003 | `Qwen3-32B` | 通用·强 |
| Qwen2.5-Coder-32B | `serve_coder32b.pbs` | 2 | 8004 | `Qwen2.5-Coder-32B-Instruct` | **代码专精·最适合可视化** |
| Qwen2.5-7B | `serve_25_7b.pbs` | 1 | 8005 | `Qwen2.5-7B-Instruct` | 通用·轻快 |
| Qwen2.5-32B | `serve_25_32b.pbs` | 2 | 8006 | `Qwen2.5-32B-Instruct` | 通用·强 |
| **Qwen3-32B-AWQ** | `serve_qwen3_32b_awq.pbs` | **1** | 8007 | `Qwen3-32B-AWQ` | **32B能力·单卡·排队快** |
| Qwen2.5-14B | `serve_25_14b.pbs` | 1 | 8008 | `Qwen2.5-14B-Instruct` | 通用·均衡 |

> 每个模型有独立的脚本/端口/日志/节点文件,互不干扰。
> 日志: `~/vllm.log`(14B)、`~/vllm_8b.log`、`~/vllm_32b.log`、`~/vllm_coder32b.log`、`~/vllm_25_7b.log`、`~/vllm_25_32b.log`、`~/vllm_32b_awq.log`、`~/vllm_25_14b.log`
> 节点文件: 对应的 `~/*_host.txt`

---

## 固定信息(每次都一样)

| 项 | 值 |
|---|---|
| 登录节点 | `login-b.cx3.hpc.ic.ac.uk`(**必须用 login-b,有 qsub**) |
| SSH 别名 | `ssh hpc`(已在 ~/.ssh/config 配好,= login-b) |
| GPU 队列 | **不要写 `#PBS -q`!** PBS 用路由队列,按 ngpus 自动选 GPU 队列;写死反而可能拖慢排队 |
| conda 激活 | `source $HOME/miniforge3/etc/profile.d/conda.sh && conda activate qwen3` |
| 单卡 GPU 变量 | `export CUDA_VISIBLE_DEVICES=0` |
| 双卡 GPU 变量 | `export CUDA_VISIBLE_DEVICES=0,1` |

> **每次节点名都会变!** 启动后务必重新查节点名,隧道命令里用最新的。
> **别连到 login-ai!** 那个节点没有 qsub。固定用 `ssh hpc`(=login-b)。
> 进 HPC 后可 `hostname` 确认显示 login-b、`which qsub` 确认有命令。
> **conda 命令找不到时**: 先 `source $HOME/miniforge3/etc/profile.d/conda.sh`
> (命令行 ssh 进来可能没自动加载 conda,VS Code Remote-SSH 会自动加载)

---

## 网络前提(Zscaler / Unified Access)

- 连 HPC 需要先开 **Zscaler**(Windows 托盘图标蓝色 = 已连)。
- WSL 能借到 Windows 的 Zscaler,**无需在 WSL 单独装**(已验证)。
- **回国后唯一变量**: Zscaler 在中国能否连通。回国前已在英国验证 WSL→Zscaler→HPC 通。
- 登录节点禁用密钥认证,**每次必须输密码 + MFA**,无法免密。

---

## 工作流(代码已在 HPC · VS Code Remote-SSH · login 节点上建隧道 · 推荐)

> **代码已迁移到 HPC**(本 FYP 项目就在 HPC 上),在 HPC 上写代码(VS Code Remote-SSH 连
> `login-b`)。但 **cx3 封了跨节点直连端口**:从 login 节点直接 `curl http://<计算节点>:8001`
> 会 `Connection refused`(即使 vllm 已绑 `0.0.0.0`,也被计算节点防火墙 REJECT)。
> **解决办法:在 login 节点上起一条端口转发隧道**(`-N` 纯转发被放行,跑命令/开 shell 会被关掉),
> 然后代码用 `localhost`。这一跳不经 WSL、不经 Zscaler。

```
VS Code (Remote-SSH → login-b) → 代码在 HPC login 节点 → 调 localhost:<端口>
                                                            │ SSH 端口转发(在 login-b 上跑)
                                                            ▼ 集群内网
                                                       计算节点的 vllm
```

**关键命令**(在 login-b 新开一个终端,挂着别关;节点名取自 `cat ~/qwen_serve_host.txt`):
```bash
ssh -N -L 8001:localhost:8001 <节点名>      # 已在 login-b 上,无需 -J;实测可放行、不需密码
# 若该命令不通,退回跳板写法: ssh -N -L 8001:localhost:8001 -J hpc jm1125@<节点名>
```

两个终端分工(都在 HPC `login-b` 上):
- 终端1: `qsub` 起服务、查节点名(`cat ~/qwen_serve_host.txt`)
- 终端2: 起隧道(上面的命令,挂着别动)
- VS Code / 终端3: 跑调用代码,`base_url` 指向 `http://localhost:<端口>/v1`

判断身在何处: `hostname` 显示 `login-b` = 在 HPC;VS Code 左下角显示 `SSH: login-b...` = Remote-SSH 已连。

> 验证: 隧道起好后 `curl http://localhost:8001/v1/models` 能返回模型列表 = 通。
> Zscaler 仍用于从笔记本 Remote-SSH / `ssh hpc` 连上 HPC 本身。

---

## (备用)本地工作流(VS Code + WSL 写代码,经隧道调 HPC)

> 仅在代码留在本地 WSL 时使用;代码已上 HPC 后日常用上面那套(在 login-b 上起隧道)。
> 区别只在隧道跑在哪、是否经 Zscaler:本地 WSL 跑隧道要经 Zscaler 且加 `-J hpc`。

```
VS Code (Remote-WSL) → 代码在 WSL → 调 localhost:<端口>
                                        │ SSH 隧道(WSL 里跑)
                                        ▼ 经 Zscaler
                                   HPC 计算节点的模型
```

三个 WSL 终端分工:
- 终端1: `ssh hpc` → qsub 起服务、查节点名
- 终端2: 开隧道(挂着别动)
- VS Code / 终端3: 跑调用代码

判断身在何处: `hostname` 显示 `login-b`=在 HPC,显示 `LAPTOP-...`=在本地 WSL。

---

## 通用启动流程(以 14B 为例,其他模型换脚本/端口/文件名)

### 方案 A: qsub 批处理(推荐日常用 · 固定可复现)

```bash
# 在 HPC 登录节点(ssh hpc 后)
qsub ~/serve_qwen.pbs              # ① 提交(换成目标模型的脚本)
qstat -u $USER                     # ② 等对应作业名变 R
cat ~/qwen_serve_host.txt          # ③ 查节点名(每次会变!换成对应 host 文件)
tail -f ~/vllm.log                 # ④ 等 "Application startup complete",Ctrl+C 退出
```

```bash
# 在 login-b 上起隧道(cx3 封跨节点直连,必须走隧道;节点名换成对应的)
ssh -N -L 8001:localhost:8001 <节点名>       # 挂着别关
# 验证: curl http://localhost:8001/v1/models
# (代码留在本地 WSL 时改为: ssh -N -L 8001:localhost:8001 -J hpc jm1125@<节点名>)
```

```bash
# 停止
qstat -u $USER          # 查作业号
qdel <作业号>           # 用完释放 GPU;不删则 8 小时后自动结束
```

### 方案 B: interactive + tmux(适合调试 · 能实时看输出)

```bash
interactive -g 1        # 申请1卡(双卡用 -g 2);若无此命令用下面原生写法
# qsub -I -l select=1:ncpus=8:mem=64gb:ngpus=1:gpu_type=L40S -l walltime=08:00:00
hostname                # 记下节点名
tmux new -s qwen        # 开 tmux
# 在 tmux 里:
source $HOME/miniforge3/etc/profile.d/conda.sh
conda activate qwen3
export CUDA_VISIBLE_DEVICES=0
vllm serve $HOME/models/Qwen3-14B --served-model-name Qwen3-14B \
  --host 0.0.0.0 --port 8001 --max-model-len 16384 --gpu-memory-utilization 0.92
# 看到 startup complete 后: Ctrl+B 然后 D (detach 丢后台)
```

tmux 操作: detach=`Ctrl+B`然后`D` | 重进=`tmux attach -t qwen` | 列表=`tmux ls`

---

## 测试调用(隧道开着时,代码用 `localhost`;端口和 model 名换成对应模型)

> 隧道把本地 `<端口>` 映射到计算节点的 vllm,所以无论代码在 HPC 还是本地 WSL,都用 `localhost`。

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen3-14B","messages":[{"role":"user","content":"你好"}]}'
```

### Python 调用
```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8001/v1", api_key="dummy")
resp = client.chat.completions.create(
    model="Qwen3-14B",   # 换成对应模型名
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)
```

> Qwen3 关思考过程: user 内容加 `/no_think`,或加 `extra_body={"chat_template_kwargs":{"enable_thinking":False}}`
> (Qwen2.5 系列无思考模式,无需此设置)

---

## 部署新模型: 只改 3~4 处

复制任一脚本,改: ①`MODEL_PATH` ②`--served-model-name` ③`PORT`/日志/host文件名
若是 32B(双卡)还要: `ngpus=2`、`CUDA_VISIBLE_DEVICES=0,1`、vllm 加 `--tensor-parallel-size 2`、ncpus/mem 加大。

---

## AWQ 量化版(Qwen3-32B-AWQ · 单卡跑 32B)

**用途**: 32B 的 BF16 版需双卡、排队久;AWQ 4-bit 量化版仅 19.3G,**单卡 L40S 就能跑**,排队快、速度快,质量轻微下降(多数场景感知不到)。日常想用 32B 又不想等双卡时用它。

**下载**(官方版,英国用 HF):
```bash
export HF_HUB_ENABLE_HF_TRANSFER=1
conda run -n qwen3 hf download Qwen/Qwen3-32B-AWQ --local-dir $HOME/models/Qwen3-32B-AWQ
# 验证: ls $HOME/models/Qwen3-32B-AWQ/*.safetensors | wc -l  → 应为 4
```

**与 BF16 双卡版的关键区别**(脚本 `serve_qwen3_32b_awq.pbs`):
- 单卡: `ngpus=1`、`CUDA_VISIBLE_DEVICES=0`、**不要** `--tensor-parallel-size`
- vllm 加: `--quantization awq_marlin`(报不支持就降为 `--quantization awq`)
- 端口 8007、日志 `vllm_32b_awq.log`、host 文件 `qwen3_32b_awq_host.txt`

**两个 32B 怎么选**: 日常用 AWQ 单卡版(快);要最高质量且愿等双卡时用 BF16 版(`serve_qwen32b.pbs`)。

---

## 下载模型: 选对来源很重要

| 你在哪 | 用哪个源 | 原因 |
|--------|---------|------|
| **英国(现在)** | HuggingFace | HF 服务器离得近,快;魔搭在中国,从英国下慢且易卡 |
| **回国后** | ModelScope(魔搭) | 魔搭在国内快,且 HF 国内常被墙 |

### HuggingFace 下载(英国推荐)
```bash
export HF_HUB_ENABLE_HF_TRANSFER=1     # 开加速(仅当前终端有效)
conda run -n qwen3 hf download Qwen/<模型名> --local-dir $HOME/models/<模型名>
# 旧命令名: huggingface-cli download ...(功能相同)
```

### ModelScope 下载(回国推荐)
```bash
conda run -n qwen3 modelscope download --model Qwen/<模型名> --local_dir $HOME/models/<模型名>
```

### 验证下载完整
```bash
ls $HOME/models/<模型名>/*.safetensors | wc -l    # 看分片数
ls $HOME/models/<模型名>/ | grep -i incomplete && echo "有残留!" || echo "完整,无残留"
```
> 各模型分片数参考: 7B/8B≈4个, 14B=8个, 32B=14~17个。
> 有 `.incomplete` 残留 = 没下完;无残留 + 分片齐 = 完整。

### 断点续传
- **同平台**重下可靠: 断了重跑同一命令,只补没下完的分片。
- **跨平台**(魔搭→HF)不保证: 可能只补缺的,也可能重下全部(不会损坏已有文件,最坏是浪费时间)。

---

## ⚠️ 重要避坑

| 坑 | 后果 | 正确做法 |
|---|---|---|
| `pip install -U ...` 升级 | 可能顶坏 huggingface_hub,导致 vLLM 下次启动报错 | 装包**不要加 `-U`**;只装需要的,留意 ERROR 版本冲突提示 |
| 修复版本冲突 | — | `conda run -n qwen3 pip install "huggingface_hub<1.0"` 降回兼容版 |
| 验证环境完好 | — | `conda run -n qwen3 python -c "import transformers; from huggingface_hub import hf_hub_download; print('OK')"` |
| 连到 login-ai | 没有 qsub | 固定 `ssh hpc`(=login-b) |
| VS Code 终端命令前红色 ⊗ | 多为 grep 等"没匹配"返回非0 | 不是真错误,看是不是搜索类命令没匹配 |

---

## 常见问题速查

| 现象 | 原因 / 解决 |
|---|---|
| `int(...'GPU-xxxx')` 报错 | 缺 `export CUDA_VISIBLE_DEVICES=0`(双卡=0,1) |
| `Address already in use` | 端口被占,换端口 |
| 直连计算节点 `Connection refused`(即使 startup complete) | cx3 封跨节点端口,**直连走不通**;必须在 login-b 上起隧道 `ssh -N -L 8001:localhost:8001 <节点名>`,代码用 `localhost` |
| `ssh <节点> '命令'` 没输出/被关 | 正常,cx3 不许在计算节点开 shell/跑命令;隧道用 `-N`(纯转发,不跑命令)才放行 |
| (备用)WSL 隧道 `Connection refused` | 用 `-J hpc` 跳板隧道,别用普通 `-L` 直连节点 |
| `~/vllm*.log` 不存在 | 作业还在排队(Q),变 R 才生成 |
| 节点 SSH 进去就 closed | 正常,cx3 限制;用 `-J` 跳板隧道访问 |
| `conda: command not found` | 先 `source $HOME/miniforge3/etc/profile.d/conda.sh` |
| `qsub: command not found` | 连到了 login-ai 等无 qsub 的节点,改用 `ssh hpc` |
| 双卡 32B 启动报 NCCL 错 | 脚本加 `export NCCL_P2P_DISABLE=1` 试试 |
| 双卡 32B 显存不足(OOM) | 调低 `--gpu-memory-utilization 0.90` 或 `--max-model-len 8192` |
| 排队太久 | 别写 `#PBS -q`(让PBS自动选队列);小模型去掉 `gpu_type` |

---

## 回国前清单

- [x] Qwen3-8B / 14B / 32B 已下载
- [x] Qwen2.5-7B / 32B / Coder-32B 已下载
- [ ] (可选)Qwen3-32B-AWQ 已下载(单卡跑 32B)
- [x] PBS 脚本已建好
- [x] SSH 别名 `hpc` 已配
- [x] 英国侧已验证 WSL 经 Zscaler 连 HPC
- [ ] **回国后第一件事: 测 `ssh hpc` 还能不能连**(唯一真实变量)
- [ ] (可选)确认 Zscaler 在中国可用,问 ICT Service Desk

---

## 一句话记住

模型权重和脚本是**常驻**的(下好就一直在);运行中的服务是**每次现起**的(代码已在 HPC: qsub 起→查节点名→在 login-b 上起隧道 `ssh -N -L 8001:localhost:8001 <节点名>`→代码用 `localhost`→qdel 或到期释放)。回国后只要 `ssh hpc` 能连上,这套流程原样可用。
