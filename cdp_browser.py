#!/usr/bin/env python3
"""
CDP浏览器客户端 - 直接通过Chrome DevTools Protocol控制浏览器
不依赖DrissionPage, 兼容所有Chrome版本
"""
import json
import time
import requests
import websocket
import threading


class CDPBrowser:
    """Chrome DevTools Protocol 客户端"""

    def __init__(self, host="127.0.0.1", port=9222):
        self.host = host
        self.port = port
        self.ws = None
        self.msg_id = 0
        self._lock = threading.Lock()
        self._connect()

    def _connect(self):
        """连接到Chrome调试端口"""
        # 获取tab列表
        resp = requests.get(f"http://{self.host}:{self.port}/json", timeout=5)
        tabs = resp.json()

        # 找到页面类型的tab, 或创建新的
        page_tab = None
        for tab in tabs:
            if tab.get("type") == "page":
                page_tab = tab
                break

        if not page_tab:
            # 创建新tab
            resp = requests.get(f"http://{self.host}:{self.port}/json/new", timeout=5)
            page_tab = resp.json()

        ws_url = page_tab["webSocketDebuggerUrl"]
        self.ws = websocket.create_connection(ws_url, timeout=30)
        print(f"  [CDP] 已连接: {page_tab.get('url', 'about:blank')}")

        # 启用必要的域
        self.send("Page.enable")
        self.send("Runtime.enable")
        self.send("Network.enable")

    def send(self, method, params=None, timeout=30):
        """发送CDP命令并等待响应"""
        with self._lock:
            self.msg_id += 1
            msg = {"id": self.msg_id, "method": method}
            if params:
                msg["params"] = params

            self.ws.send(json.dumps(msg))

            # 等待匹配的响应
            deadline = time.time() + timeout
            while time.time() < deadline:
                self.ws.settimeout(max(1, deadline - time.time()))
                try:
                    raw = self.ws.recv()
                    data = json.loads(raw)

                    # 匹配响应ID
                    if "id" in data and data["id"] == self.msg_id:
                        if "error" in data:
                            err = data["error"]
                            return {"error": err.get("message", str(err))}
                        return data.get("result", {})

                    # 忽略事件消息
                except websocket.WebSocketTimeoutException:
                    return {"error": "timeout"}
                except Exception as e:
                    return {"error": str(e)}

            return {"error": "timeout"}

    def navigate(self, url, wait_sec=2):
        """导航到URL"""
        self.send("Page.navigate", {"url": url})
        time.sleep(wait_sec)

    def evaluate(self, js_expression):
        """执行JavaScript并返回结果"""
        result = self.send("Runtime.evaluate", {
            "expression": js_expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if "error" in result:
            return None
        val = result.get("result", {})
        if val.get("type") == "undefined":
            return None
        return val.get("value")

    def get_html(self):
        """获取页面HTML"""
        return self.evaluate("document.documentElement.outerHTML")

    def get_url(self):
        """获取当前URL"""
        return self.evaluate("window.location.href")

    def get_title(self):
        """获取页面标题"""
        return self.evaluate("document.title")

    def scroll_down(self):
        """滚动到底部"""
        self.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    def scroll_up(self):
        """滚动到顶部"""
        self.evaluate("window.scrollTo(0, 0)")

    def block_resources(self, patterns=None):
        """屏蔽资源加载"""
        if patterns is None:
            patterns = [
                "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.svg", "*.ico", "*.bmp",
                "*.mp4", "*.webm", "*.avi", "*.mov", "*.flv", "*.m3u8", "*.ts",
                "*.mp3", "*.wav", "*.ogg", "*.aac", "*.m4a",
                "*.woff", "*.woff2", "*.ttf", "*.eot",
            ]
        self.send("Network.setBlockedURLs", {"urls": patterns})
        print(f"  [CDP] 资源屏蔽: {len(patterns)}个模式")

    def set_user_agent(self, ua):
        """设置User-Agent"""
        self.send("Network.setUserAgentOverride", {"userAgent": ua})

    def get_cookies(self):
        """获取cookies"""
        result = self.send("Network.getCookies")
        return result.get("cookies", [])

    def close(self):
        """关闭连接"""
        if self.ws:
            self.ws.close()


def ensure_chrome(port=9222):
    """确保Chrome以调试端口运行"""
    import subprocess
    import os

    # 检查端口是否已可用
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
        if resp.status_code == 200:
            print(f"  [Chrome] 调试端口 {port} 已就绪")
            return True
    except Exception:
        pass

    # 启动Chrome
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not os.path.exists(chrome_path):
        print("  [Chrome] 未找到Chrome浏览器!")
        return False

    subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--user-data-dir=/tmp/chrome_scrape",
        "--window-size=1920,1080",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 等待端口就绪
    for _ in range(10):
        time.sleep(1)
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
            if resp.status_code == 200:
                print(f"  [Chrome] 调试端口 {port} 已启动")
                return True
        except Exception:
            pass

    print("  [Chrome] 启动失败!")
    return False
