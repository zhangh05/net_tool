# NetOps 认证接口文档

## 接口列表

### POST /api/projects/{project_id}/login

登录项目，验证用户名/密码后创建 session。

**请求体：**
```json
{
  "username": "admin",
  "password": "admin"
}
```

**返回：**
```json
{
  "status": "ok",
  "token": "xxx",
  "username": "admin",
  "role": "super",
  "project_id": null,
  "message": "超级管理员登录成功"
}
```

---

### POST /api/projects/{project_id}/logout

销毁当前 session。

**请求头：** `X-Session-Token: <token>`

**返回：**
```json
{
  "status": "ok",
  "message": "已退出登录"
}
```

---

### GET /api/auth/verify?token=xxx

验证 session token，返回用户信息。供其他工具（锚点、ConfigBak、Terminal 等）验证 NetOps session。

**参数：** `token` (query string)

**返回成功：**
```json
{
  "valid": true,
  "username": "admin",
  "role": "super",
  "project_id": null
}
```

**返回失败：**
```json
{
  "valid": false,
  "error": "会话已过期或不存在"
}
```
