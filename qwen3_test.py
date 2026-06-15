from openai import OpenAI

# cx3 封跨节点直连端口,需在 login-b 上起隧道: ssh -N -L 8001:localhost:8001 <节点名>
# 隧道把本地 8001 映射到计算节点的 vllm,所以这里用 localhost
client = OpenAI(base_url="http://localhost:8001/v1", api_key="dummy")
resp = client.chat.completions.create(
    model="Qwen3-14B",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)