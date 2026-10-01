"""Local-only HTTP workbench. Start with python app.py."""
import argparse
import hmac
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import traceback
from urllib.parse import urlsplit
import webbrowser
import zipfile

from check_course import parse_json, require
import workbench as work


TOKEN = secrets.token_urlsafe(32)
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/lesson.js": ("lesson.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    server_version = "LessonProof/0.2"

    def send(self, data, content_type="application/json; charset=utf-8", status=200, filename=None):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def trusted_request(self):
        port = self.server.server_port
        hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
        require(self.headers.get("Host") in hosts, "仅允许从本机工作台访问")
        origin = self.headers.get("Origin")
        require(origin is None or origin in {f"http://{host}" for host in hosts}, "请求来源不匹配")
        if urlsplit(self.path).path.startswith("/api/"):
            require(hmac.compare_digest(self.headers.get("X-LessonProof-Token", ""), TOKEN), "页面会话已更新，请刷新")

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)

    def dispatch(self, post):
        try:
            self.trusted_request()
            path = urlsplit(self.path).path
            if post:
                require(self.headers.get("Transfer-Encoding") is None, "不支持分块上传")
                length = int(self.headers.get("Content-Length", "0"))
                require(0 < length <= 16 * 1024 * 1024, "请求内容应为 1 字节至 16 MiB")
                self.connection.settimeout(15)
                data = self.rfile.read(length)
                require(len(data) == length, "上传尚未完成")
                if path == "/api/upload":
                    require(self.headers.get("Content-Type") == "application/zip", "请上传 ZIP 课程包")
                    return self.send(work.create_job(upload=data), status=201)
                require(self.headers.get("Content-Type") == "application/json", "请求内容格式无效")
                body = parse_json(data)
                require(isinstance(body, dict), "请求需要 JSON 对象")
                if path == "/api/jobs":
                    return self.send(work.create_job(sample=body.get("sample")), status=201)
                pieces = path.split("/")
                require(len(pieces) == 5 and pieces[1:3] == ["api", "jobs"], "操作不存在")
                identifier, action = pieces[3:]
                version = body.get("version_hash")
                require(isinstance(version, str), "请求缺少材料版本")
                if action == "run":
                    result = work.begin_run(identifier, version, body.get("confirmed"))
                elif action == "apply":
                    result = work.apply_proposal(identifier, version)
                elif action == "approve":
                    result = work.approve(identifier, version, body.get("confirmed"))
                elif action == "resolve":
                    result = work.resolve_findings(identifier, version, body.get("reason"))
                elif action == "deliver":
                    result = work.deliver(identifier, version)
                else:
                    raise ValueError("操作不存在")
                return self.send(result)
            if path in ASSETS:
                name, kind = ASSETS[path]
                data = (work.ROOT / "web" / name).read_bytes()
                if path == "/":
                    data = data.replace(b"__SESSION_TOKEN__", TOKEN.encode())
                return self.send(data, kind)
            if path == "/favicon.ico":
                return self.send(b"", "image/x-icon", status=204)
            if path == "/api/status":
                return self.send(work.status())
            if path == "/api/jobs":
                return self.send(work.list_jobs())
            pieces = path.split("/")
            if len(pieces) >= 4 and pieces[1:3] == ["api", "jobs"]:
                identifier = pieces[3]
                if len(pieces) == 4:
                    return self.send(work.detail(identifier))
                if len(pieces) == 5 and pieces[4] == "evidence.zip":
                    return self.send(work.evidence_zip(identifier), "application/zip", filename="lessonproof-evidence.zip")
                if len(pieces) == 5 and pieces[4] in ("course.zip", "receipt.json"):
                    file = work.delivery_file(identifier, pieces[4])
                    return self.send(file.read_bytes(), "application/octet-stream", filename=pieces[4])
            if len(pieces) == 3 and pieces[1] == "student":
                job = work.load(pieces[2])
                archive = work.delivery_file(pieces[2], "course.zip")
                require(work.sha(archive.read_bytes()) == job["delivery"]["zip_sha256"], "交付文件校验失败")
                with zipfile.ZipFile(archive) as bundle:
                    lesson = bundle.read("lesson.md").decode("utf-8")
                    notebook = parse_json(bundle.read("lesson.ipynb"))
                code = "".join(f'<section class="student-step"><h2>{escape(cell["id"])}</h2><pre>{escape(work.source_text(cell))}</pre></section>'
                               for cell in notebook["cells"] if cell["cell_type"] == "code")
                page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>课程阅读 · LessonProof</title><link rel="stylesheet" href="/style.css"><script src="/lesson.js" defer></script><body class="student"><main>'
                page += f'<a class="brand" href="/">LessonProof<span>课程阅读</span></a><p class="eyebrow">教师已审核 · 版本 {job["revision"] + 1}</p><h1>{escape(job["title"])}</h1><article id="student-lesson" class="lecture lesson-text">{escape(lesson)}</article>{code}<footer>内容来自已交付课程包，文件校验一致。</footer></main></body></html>'
                return self.send(page.encode("utf-8"), "text/html; charset=utf-8")
            self.send({"error": "页面不存在"}, status=404)
        except zipfile.BadZipFile:
            self.send({"error": "这个文件无法读取为 ZIP 课程包，请重新打包后导入。"}, status=400)
        except (ValueError, KeyError, TypeError) as error:
            self.send({"error": str(error)}, status=400)
        except OSError as error:
            self.send({"error": "文件或本地服务暂不可用：" + str(error)}, status=503)
        except Exception:
            traceback.print_exc()
            self.send({"error": "本次操作未完成，详细原因已写入服务日志。"}, status=500)

    def log_message(self, format, *args):
        if len(args) > 1 and str(args[1]) not in ("200", "201"):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="LessonProof 本地教师工作台")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    print(f"LessonProof 已启动：http://127.0.0.1:{args.port}  （Ctrl+C 停止）", flush=True)
    if args.open:
        webbrowser.open(f"http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        work.POOL.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
