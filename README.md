# shen-meme-api (minimal)

一个极简的表情包生成 API（FastAPI）。

## Base URL
把 `{HOST}` 换成你的地址，例如：`http://47.105.107.105:8000`

## API

### Health Check
**GET** `/health`

示例：
```bash
curl "{HOST}/health"
返回示例：

json
复制代码
{"ok":true,"template":"template.jpg"}
Generate Meme
GET /meme?qq=1234567&name=test

参数：

qq：QQ号（必填，数字）

name：展示昵称（可选；不传就用 qq）

返回：

image/png

Linux/macOS：

bash
复制代码
curl -o shen.png "{HOST}/meme?qq=1234567&name=test"
Windows PowerShell：

powershell
复制代码
iwr "{HOST}/meme?qq=1234567&name=test" -OutFile shen.png
Notes
图片下载到你运行命令的当前目录。

如果提示 Connection refused，说明服务未启动或端口未开放。

makefile
复制代码
::contentReference[oaicite:0]{index=0}