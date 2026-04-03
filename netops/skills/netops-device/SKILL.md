# NetOps Device Skill - 网络设备操控技能

## 定位

让 AI 能够像资深网络工程师一样，通过 Telnet/SSH 连接网络设备，执行配置命令，并处理交互式输出。

## 核心能力

- 多厂商支持（华为 H3C/华为/思科，通过 device-handler 适配）
- 多会话管理（连接池，支持同时操作多台设备）
- 交互式命令处理（等待提示符、`[Y/N]` 确认、多跳登录）
- 命令执行结果结构化返回

## AI 操作原语

| action | 说明 | 必需参数 |
|--------|------|----------|
| `device_connect` | 建立 Telnet/SSH 会话 | `device_id`, `protocol`, `ip`, `port`, `user`, `password` |
| `device_send` | 发送命令 | `session_id`, `cmd` |
| `device_expect` | 等待特定输出才继续 | `session_id`, `pattern`, `timeout_ms` |
| `device_wait` | 延时等待 | `session_id`, `ms` |
| `device_close` | 关闭会话 | `session_id` |
| `device_batch` | 批量执行多条命令 | `session_id`, `commands[]` |

## 工作循环示例

```
用户: "telnet 195.168.32.27:30007，查看型号和版本"

AI 调用:
{
  "action": "device_connect",
  "device_id": "n1775151536920nndrz",   // 拓扑中的设备节点 ID（可选）
  "protocol": "telnet",
  "ip": "195.168.32.27",
  "port": 30007,
  "user": "admin",
  "password": "admin123"
}
→ { "ok": true, "session_id": "ds_001", "prompt": "[设备]" }

{
  "action": "device_send",
  "session_id": "ds_001",
  "cmd": "display version"
}
→ { "ok": true, "output": "..." }

{
  "action": "device_close",
  "session_id": "ds_001"
}
→ { "ok": true }
```

## 会话上下文

```javascript
{
  "session_id": "ds_001",
  "device_id": "n1775151536920nndrz",
  "ip": "195.168.32.27",
  "port": 30007,
  "protocol": "telnet",
  "vendor": "huawei",         // 自动识别
  "prompt": "[设备]",          // 当前提示符
  "last_output": "...",
  "history": [],              // 命令历史
  "created_at": "12:09:00"
}
```

## 设备类型自动识别

通过首次登录后的提示符识别厂商：
- 华为：`[设备名]` 或 `[设备名-视图]`
- H3C：`<设备名>` 或 `[H3C-视图]`
- 思科：`设备名>` 或 `设备名(config)#`

## OpSkill 注册名

`netops_device` — 在 `OpSkills` 注册表中的名称

## 后续扩展方向

- `device_validate`: 配置前安全检查（是否影响业务）
- `device_compare`: 配置前后对比
- `device_template`: 执行预定义配置模板
- 多设备批量操作（并发连接多台）
