"""
微信公众号草稿箱中转服务
"""

from flask import Flask, request, jsonify
import requests
import re
import io

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

def upload_thumb(access_token, thumb_url):
    if not thumb_url:
        return None
    img_resp = requests.get(thumb_url, timeout=30)
    img_resp.raise_for_status()
    files = {"media": ("thumb.jpg", io.BytesIO(img_resp.content), "image/jpeg")}
    resp = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image",
        files=files,
        timeout=30
    )
    result = resp.json()
    if "media_id" in result:
        return result["media_id"]
    else:
        raise Exception(f"上传图片失败: {result}")

@app.route("/upload_thumb", methods=["POST"])
def upload_thumb_endpoint():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"errcode": 400, "errmsg": "请求体为空"}), 400
        appid = body.get("appid")
        appsecret = body.get("appsecret")
        thumb_url = body.get("thumb_url")
        if not appid or not appsecret:
            return jsonify({"errcode": 400, "errmsg": "缺少 appid 或 appsecret"}), 400
        if not thumb_url:
            return jsonify({"errcode": 400, "errmsg": "缺少 thumb_url"}), 400
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
            return jsonify({"errcode": 400, "errmsg": "请求体为空"}), 400
        appid = body.get("appid")
        appsecret = body.get("appsecret")
        if not appid or not appsecret:
            return jsonify({"errcode": 400, "errmsg": "缺少 appid 或 appsecret"}), 400
        title = body.get("title", "无标题")
        content = body.get("content", "")
        author = body.get("author", "")
        dig
