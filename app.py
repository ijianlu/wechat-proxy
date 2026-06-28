# 微信公众号草稿箱中转服务 - 修复版
# 修复内容：解决中文被转义为 \uXXXX 的问题
# 部署方法：将此文件替换 GitHub 仓库中的 app.py，Render 会自动重新部署

"""
微信公众号草稿箱中转服务（修复版）
修复了中文内容被转义为 \\uXXXX 的问题
"""

from flask import Flask, request, jsonify
import requests
import re
import io
import json

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
        raise Exception(f"获取 access_token 失败: {data}")

def filter_html(content):
    """移除 script 和 style 标签"""
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    return content

def upload_thumb(access_token, thumb_url):
    """上传图片到微信素材库，返回 media_id"""
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
        raise Exception(f"上传图片失败: {result}")

@app.route("/upload_thumb", methods=["POST"])
def upload_thumb_endpoint():
    """上传封面图，返回 thumb_media_id"""
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
    """创建微信公众号草稿"""
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
        # 【关键修复】使用 ensure_ascii=False 防止中文被转义为 \\uXXXX
        # 使用 data= 而不是 json=，避免 requests 内部再次调用 json.dumps
        payload_str = json.dumps({"articles": articles}, ensure_ascii=False)
        resp = requests.post(
            f"{WX_DRAFT_URL}?access_token={access_token}",
            data=payload_str.encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=utf-8'},
            timeout=30
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
    """查询 Render 服务器出口 IP"""
    try:
        resp = requests.get("https://api.ipify.org?format=json", timeout=10)
        return resp.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    """健康检查"""
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
