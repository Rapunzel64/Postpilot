"""LinkedIn API client for PostPilot.
Handles profile authentication, direct posting, media uploads, and error diagnostics.
"""
import base64
import json
import logging
import re
from typing import Dict, Optional, Tuple
import requests

logger = logging.getLogger(__name__)


def extract_image_bytes(img_str: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Extracts raw binary bytes and mime type from a base64 data URI or raw base64 string."""
    if not img_str or not isinstance(img_str, str):
        return None, None
    try:
        if "," in img_str and img_str.startswith("data:"):
            header, _, data = img_str.partition(",")
            mime = "image/jpeg"
            m = re.match(r"data:([^;]+);base64", header)
            if m:
                mime = m.group(1)
            raw = base64.b64decode(data)
            return raw, mime
        # Try raw base64 if no prefix
        raw = base64.b64decode(img_str)
        return raw, "image/jpeg"
    except Exception as e:
        logger.warning(f"Could not decode image string: {e}")
        return None, None


def get_user_profile(token: str) -> Dict:
    """Fetches LinkedIn user profile and member URN using the access token.
    Supports OpenID Connect (/v2/userinfo) and legacy (/v2/me).
    """
    token = (token or "").strip()
    if not token:
        return {"success": False, "error": "LinkedIn access token is missing."}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 1. Try modern OpenID Connect userinfo endpoint
    try:
        r = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            sub = data.get("sub", "")
            name = data.get("name") or f"{data.get('given_name', '')} {data.get('family_name', '')}".strip()
            picture = data.get("picture", "")
            return {
                "success": True,
                "urn": f"urn:li:person:{sub}",
                "name": name or "LinkedIn User",
                "picture": picture,
                "email": data.get("email", ""),
            }
    except Exception as e:
        logger.debug(f"Userinfo endpoint failed: {e}")

    # 2. Try legacy /v2/me endpoint
    try:
        r = requests.get("https://api.linkedin.com/v2/me", headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            uid = data.get("id", "")
            first = data.get("localizedFirstName", "")
            last = data.get("localizedLastName", "")
            name = f"{first} {last}".strip()
            return {
                "success": True,
                "urn": f"urn:li:person:{uid}",
                "name": name or "LinkedIn User",
                "picture": "",
            }
        else:
            err_text = r.text
            try:
                err_json = r.json()
                msg = err_json.get("message") or err_json.get("error_description") or err_text
            except Exception:
                msg = err_text
            return {
                "success": False,
                "error": f"LinkedIn returned HTTP {r.status_code}: {msg[:200]}",
            }
    except Exception as e:
        return {"success": False, "error": f"Connection error: {str(e)}"}


def register_upload(token: str, author_urn: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Registers an image upload with LinkedIn assets API.
    Returns (asset_urn, upload_url, error_message).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": author_urn,
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }
            ],
        }
    }
    try:
        r = requests.post(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            headers=headers,
            json=payload,
            timeout=25,
        )
        if r.status_code in (200, 201):
            val = r.json().get("value", {})
            asset = val.get("asset")
            mechanism = val.get("uploadMechanism", {}).get(
                "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}
            )
            upload_url = mechanism.get("uploadUrl")
            return asset, upload_url, None
        return None, None, f"Asset registration failed ({r.status_code}): {r.text[:200]}"
    except Exception as e:
        return None, None, f"Asset registration exception: {str(e)}"


def upload_binary_image(upload_url: str, token: str, image_bytes: bytes, mime_type: str = "image/jpeg") -> Tuple[bool, Optional[str]]:
    """Uploads binary image bytes to LinkedIn's pre-signed upload URL."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": mime_type,
    }
    try:
        r = requests.put(upload_url, headers=headers, data=image_bytes, timeout=45)
        if r.status_code in (200, 201):
            return True, None
        return False, f"Image upload failed ({r.status_code}): {r.text[:200]}"
    except Exception as e:
        return False, f"Image upload exception: {str(e)}"


def publish_post(
    token: str,
    text: str,
    image_bytes: Optional[bytes] = None,
    mime_type: str = "image/jpeg",
    author_urn: Optional[str] = None,
) -> Dict:
    """Publishes a post directly to LinkedIn.
    Supports text-only and text + image posts.
    """
    token = (token or "").strip()
    if not token:
        return {"success": False, "error": "No LinkedIn access token provided."}

    text = (text or "").strip()
    if not text:
        return {"success": False, "error": "Post text cannot be empty."}

    # If author_urn is not specified, resolve it via profile endpoint
    if not author_urn:
        profile = get_user_profile(token)
        if not profile.get("success"):
            return {
                "success": False,
                "error": f"Failed to authenticate with LinkedIn: {profile.get('error')}. Please verify your access token.",
            }
        author_urn = profile["urn"]

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }

    asset_urn = None
    if image_bytes:
        asset_urn, upload_url, err = register_upload(token, author_urn)
        if asset_urn and upload_url:
            ok, up_err = upload_binary_image(upload_url, token, image_bytes, mime_type)
            if not ok:
                logger.warning(f"Failed to upload image binary, proceeding with text-only post: {up_err}")
                asset_urn = None
        else:
            logger.warning(f"Could not register image upload ({err}), proceeding with text-only post.")
            asset_urn = None

    # Construct UGC Post payload
    if asset_urn:
        share_content = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "IMAGE",
            "media": [
                {
                    "status": "READY",
                    "description": {"text": "Illustration"},
                    "media": asset_urn,
                    "title": {"text": "Post Visual"},
                }
            ],
        }
    else:
        share_content = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "NONE",
        }

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": share_content
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    try:
        r = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if r.status_code in (200, 201):
            res_data = r.json()
            post_id = res_data.get("id", "")
            return {
                "success": True,
                "post_id": post_id,
                "author": author_urn,
                "has_image": bool(asset_urn),
                "message": "Successfully published to LinkedIn! 🎉",
            }

        # Handle REST API fallback if ugcPosts returned 404 or 400 with specific schema error
        if r.status_code in (404, 400):
            # Try /rest/posts API
            rest_headers = {
                "Authorization": f"Bearer {token}",
                "LinkedIn-Version": "202401",
                "Content-Type": "application/json",
            }
            rest_payload = {
                "author": author_urn,
                "commentary": text,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }
            r_rest = requests.post(
                "https://api.linkedin.com/rest/posts",
                headers=rest_headers,
                json=rest_payload,
                timeout=30,
            )
            if r_rest.status_code in (200, 201):
                post_id = r_rest.headers.get("x-restli-id", "")
                return {
                    "success": True,
                    "post_id": post_id,
                    "author": author_urn,
                    "has_image": False,
                    "message": "Successfully published to LinkedIn! 🎉",
                }

        # Parse error
        err_msg = r.text
        try:
            err_json = r.json()
            err_msg = err_json.get("message") or err_json.get("error_description") or err_msg
        except Exception:
            pass
        return {
            "success": False,
            "error": f"LinkedIn returned HTTP {r.status_code}: {err_msg}",
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to post to LinkedIn: {str(e)}"}
