# 微信公众号草稿箱中转服务 - v3
# 修复内容：
# 1. 解决中文被转义为 \uXXXX 的问题
# 2. 自动上传文章内外部图片到微信服务器
# 3. 支持尾图自动拼接

from flask import Flask, request, jsonify
import requests
import re
import io
import json

app = Flask(__name__)

WX_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WX_DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
WX_UPLOAD_IMG = "https://api.weixin.qq.com/cgi-bin/material/add_material"
WX_UPLOAD_ARTICLE_IMG = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"

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
    """上传图片到微信素材库，返回 media_id（用于封面图）"""
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
        raise Exception(f"上传封面图失败: {result}")

def upload_article_image(access_token, img_url):
    """上传文章内嵌图片到微信服务器（从URL下载），返回微信CDN URL"""
    img_resp = requests.get(img_url, timeout=30)
    img_resp.raise_for_status()
    content_type = img_resp.headers.get('Content-Type', '')
    if 'png' in content_type:
        ext, mime = 'png', 'image/png'
    elif 'gif' in content_type:
        ext, mime = 'gif', 'image/gif'
    else:
        ext, mime = 'jpg', 'image/jpeg'
    return _upload_article_image_bytes(access_token, img_resp.content, ext, mime)

def upload_article_image_from_base64(access_token, b64_data, mime="image/png"):
    """上传文章内嵌图片到微信服务器（从base64），返回微信CDN URL"""
    import base64
    img_bytes = base64.b64decode(b64_data)
    ext = 'png' if 'png' in mime else 'jpg'
    return _upload_article_image_bytes(access_token, img_bytes, ext, mime)

def _upload_article_image_bytes(access_token, img_bytes, ext, mime):
    """上传图片字节数据到微信服务器，返回微信CDN URL"""
    files = {"media": (f"article_img.{ext}", io.BytesIO(img_bytes), mime)}
    resp = requests.post(
        f"{WX_UPLOAD_ARTICLE_IMG}?access_token={access_token}",
        files=files,
        timeout=30
    )
    result = resp.json()
    if "url" in result:
        return result["url"]
    else:
        raise Exception(f"上传文章图片失败: {result}")

def process_content_images(access_token, content):
    """自动将 content 中的外部图片URL替换为微信CDN URL"""
    img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
    matches = img_pattern.findall(content)
    seen = {}
    for img_url in matches:
        if img_url in seen:
            content = content.replace(img_url, seen[img_url])
            continue
        if 'mmbiz.qpic.cn' in img_url or 'wx.qlogo.cn' in img_url:
            continue
        try:
            wx_url = upload_article_image(access_token, img_url)
            seen[img_url] = wx_url
            content = content.replace(img_url, wx_url)
        except Exception as e:
            print(f"上传图片 {img_url} 失败: {e}")
    return content

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

@app.route("/upload_article_img", methods=["POST"])
def upload_article_img_endpoint():
    """上传文章内嵌图片，返回微信CDN URL。支持 img_url 或 image_base64"""
    try:
        body = request.get_json()
        if not body:
            return jsonify({"errcode": 400, "errmsg": "请求体为空"}), 400
        appid = body.get("appid")
        appsecret = body.get("appsecret")
        img_url = body.get("img_url")
        img_b64 = body.get("image_base64")
        mime_type = body.get("mime_type", "image/png")
        if not appid or not appsecret:
            return jsonify({"errcode": 400, "errmsg": "缺少 appid 或 appsecret"}), 400
        access_token = get_access_token(appid, appsecret)
        if img_b64:
            wx_url = upload_article_image_from_base64(access_token, img_b64, mime_type)
        elif img_url:
            wx_url = upload_article_image(access_token, img_url)
        else:
            return jsonify({"errcode": 400, "errmsg": "缺少 img_url 或 image_base64"}), 400
        return jsonify({"errcode": 0, "errmsg": "ok", "url": wx_url})
    except Exception as e:
        return jsonify({"errcode": 500, "errmsg": str(e)}), 500

@app.route("/add_draft", methods=["POST"])
def add_draft():
    """创建微信公众号草稿 - 自动处理文章内图片"""
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
        footer_img_url = body.get("footer_img_url", "")
        footer_img_base64 = body.get("footer_img_base64", "")
        header_img_url = body.get("header_img_url", "")
        header_img_base64 = body.get("header_img_base64", "")
        content = filter_html(content)
        access_token = get_access_token(appid, appsecret)
        if thumb_url and not thumb_media_id:
            thumb_media_id = upload_thumb(access_token, thumb_url)
        # 自动拼接头图
        if header_img_base64:
            wx_header_url = upload_article_image_from_base64(access_token, header_img_base64, "image/gif")
            content = f'<p style="text-align:center;margin:0 0 20px 0;text-indent:0;padding:0;"><img src="{wx_header_url}" style="max-width:100%;" /></p>' + content
        elif header_img_url:
            content = f'<p style="text-align:center;margin:0 0 20px 0;text-indent:0;padding:0;"><img src="{header_img_url}" style="max-width:100%;" /></p>' + content
        # 自动拼接尾图
        if footer_img_base64:
            wx_footer_url = upload_article_image_from_base64(access_token, footer_img_base64, "image/png")
            content += f'<p style="text-align:center;margin:30px 0 10px 0;text-indent:0;padding:0;"><img src="{wx_footer_url}" style="max-width:100%;" /></p>'
        elif footer_img_url:
            content += f'<p style="text-align:center;margin:30px 0 10px 0;text-indent:0;padding:0;"><img src="{footer_img_url}" style="max-width:100%;" /></p>'
        # 自动上传文章内的外部图片
        content = process_content_images(access_token, content)
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
