# shen-meme-api (minimal)

一个极简的表情包生成插件

## Base URL

把 `{HOST}` 换成你的地址，例如：`http://47.105.107.105:8000`

## API

### Health Check

**GET** `/health`

```bash
curl "{HOST}/health"
```

返回示例：

```json
{"ok": true, "template": "template.jpg"}
```

### Generate Meme

**GET** `/meme?qq=1234567&name=test`

参数：

- `qq`：QQ 号（必填，数字）
- `name`：展示昵称（可选；不传就用 `qq`）

返回：

- Content-Type: `image/png`

Linux/macOS：

```bash
curl -o shen.png "{HOST}/meme?qq=1234567&name=test"
```

Windows PowerShell：

```powershell
iwr "{HOST}/meme?qq=1234567&name=test" -OutFile shen.png
```

## Notes

- 图片会下载到你运行命令的当前目录。
- 如果提示 `Connection refused`，通常是服务未启动、端口未监听或安全组/防火墙未放行。
