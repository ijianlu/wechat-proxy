"""
微信公众号草稿箱中转服务
"""

from flask import Flask, request, jsonify
import requests
import re

app = Flask(__name__)

WX_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WX_DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"

_token_cache = {"token": None, "expires_at": 0}

def get_access_token(appid, appsecret):
    import time
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]
    resp = requests.get(
        WX_TOKEN_URL,
        params={"grant_type": "client_credential", "appid": appid, "secret": appsecret},
        timeout=10
    )
    data = resp.json()
    if "access_token" in data:
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = now + 7000
        return data["access_token"]
    else:
        raise Exception(f"获取 access_token 失败: {data}")

def filter_html(content):
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    return content

@app.route("/add_draft", methods=["POST"])
def add_draft():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"errcode": 400, "errmsg": "请求体为空"}), 400
        appid = body.get("appid")
        appsecret = body.get("appsecret")
        if not appid or not appsecret:
            return jsonify({"errcode": 400, "errmsg": "缺少 appid 或 appsecret"}), 400
        title = body.get("title", "无标题")
        content = body.get("content", "")
        author = body.get("author", "")
        digest = body.get("digest", "")
        thumb_url = body.get("thumb_url", "")
        content = filter_html(content)
        access_token = get_access_token(appid, appsecret)
        articles = [{
            "title": title,
            "author": author,
            "digest": digest,
            "content": content,
            "content_source_url": "",
            "thumb_url": thumb_url,
            "need_open_comment": 0,
            "only_fans_can_comment": 0
        }]
        resp = requests.post(
            f"{WX_DRAFT_URL}?access_token={access_token}",
            json={"articles": articles},
            timeout=15
        )
        result = resp.json()
        if result.get("errcode") == 0:
            return jsonify({"errcode": 0, "errmsg": "ok", "media_id": result.get("media_id")})
        else:
            return jsonify(result)
    except Exception as e:
        return jsonify({"errcode": 500, "errmsg": str(e)}), 500

@app.route("/myip", methods=["GET"])
def myip():
    try:
        resp = requests.get("https://api.ipify.org?format=json", timeout=10)
        return resp.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
