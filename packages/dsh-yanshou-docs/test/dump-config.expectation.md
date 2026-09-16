# `--dump-config` 期望片段（不是一次真实 dump）

本文件列出 **P3 DoD 在 `dsh --profile yanshou --dump-config` 上要看到的文本**。
它**不是**某次运行的抄本。真跑成功时把输出另存；没有 `dsh` 时不要把本文件当成实测证据。

## 层头

```
# == dsh-yanshou-docs
```

## 本包插件行

```yaml
- id: yanshou-docs
  name: dsh-yanshou-docs
```

## profile bundles

```json
["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-sdk-app", "dsh-yanshou-docs"]
```

（`plugin add` 会把第三项追加到 `--from-default-profile sdk` 已经写入的前两项之后。）

## JSON-RPC（来自 sdk 模板，不是本包 insert）

```yaml
- id: sdk-jsonrpc-server
  name: '@deepseek-ai/dsh-sdk-jsonrpc-server'
```

## 本包覆盖后不应再出现

- `personaPrefix: You are a coding agent powered by the {{model}} model.`
- `model: deepseek-chat`
- 任何 `sk-` / `apiKey:` 明文
