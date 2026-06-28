"""
寰俊鍏紬鍙疯崏绋跨涓浆鏈嶅姟
"""

from flask import Flask, request, jsonify
import requests
import re
import io

app = Flask(__name__)

WX_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WX_DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
WX_UPLOAD_IMG = "https://api.weixin.qq.com/cgi-bin/material/add_material"

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
        raise Exception(f"鑾峰彇 access_token 澶辫触: {data}")

def filter_html(content):
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    return content

def upload_thumb(access_token, thumb_url):
    if not thumb_url:
        return None
    img_resp = requests.get(thumb_url, timeout=30)
    img_resp.raise_for_status()
    files = {"media": ("thumb.jpg", io.BytesIO(img_resp.content), "image/jpeg")}
    resp = requests.post(
        f"{WX_UPLOAD_IMG}?access_token={access_token}&type=image",
        files=files,
        timeout=30
    )
    result = resp.json()
    if "media_id" in result:
        return result["media_id"]
    else:
        raise Exception(f"涓婁紶鍥剧墖澶辫触: {result}")

@app.route("/upload_thumb", methods=["POST"])
def upload_thumb_endpoint():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"errcode": 400, "errmsg": "璇锋眰浣撲负绌�"}), 400
        appid = body.get("appid")
        appsecret = body.get("appsecret")
        thumb_url = body.get("thumb_url")
        if not appid or not appsecret:
            return jsonify({"errcode": 400, "errmsg": "缂哄皯 appid 鎴� appsecret"}), 400
        if not thumb_url:
            return jsonify({"errcode": 400, "errmsg": "缂哄皯 thumb_url"}), 400
        access_token = get_access_token(appid, appsecret)
        media_id = upload_thumb(access_token, thumb_url)
        return jsonify({"errcode": 0, "errmsg": "ok", "media_id": media_id})
    except Exception as e:
        return jsonify({"errcode": 500, "errmsg": str(e)}), 500

@app.route("/add_draft", methods=["POST"])
def add_draft():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"errcode": 400, "errmsg": "璇锋眰浣撲负绌�"}), 400
        appid = body.get("appid")
        appsecret = body.get("appsecret")
        if not appid or not appsecret:
            return jsonify({"errcode": 400, "errmsg": "缂哄皯 appid 鎴� appsecret"}), 400
        title = body.get("title", "鏃犳爣棰�")
        content = body.get("content", "")
        author = body.get("author", "")
        digest = body.get("digest", "")
        thumb_media_id = body.get("thumb_media_id", "")
        thumb_url = body.get("thumb_url", "")
        content = filter_html(content)
        access_token = get_access_token(appid, appsecret)
        if thumb_url and not thumb_media_id:
            thumb_media_id = upload_thumb(access_token, thumb_url)
        articles = [{
            "title": title,
            "author": author,
            "digest": digest,
            "content": content,
            "content_source_url": "",
            "thumb_media_id": thumb_media_id,
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
