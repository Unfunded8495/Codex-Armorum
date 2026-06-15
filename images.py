"""Reference image fetching, validation, caching, and upload handling."""
import ipaddress
import os
import re
import socket
import urllib.request
from urllib.parse import urlparse

from data_store import get_store

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE, "cache", "images")
ALLOWED = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_REF_BYTES = 12 * 1024 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
REF_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _name_slug(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def _ref_candidates(did):
    store = get_store()
    d = store.ds_by_id.get(did)
    slugs = [did]
    if d:
        legacy_slug = _name_slug(d["name"])
        if legacy_slug and legacy_slug not in slugs:
            slugs.append(legacy_slug)
    return slugs


def _ref_path(did):
    if os.path.exists(os.path.join(CACHE_DIR, did + ".none")):
        return None
    for base in _ref_candidates(did):
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            p = os.path.join(CACHE_DIR, base + ext)
            if os.path.exists(p):
                return p
    return None


def _clear_ref(did, include_legacy=False, mark_cleared=False):
    bases = _ref_candidates(did) if include_legacy else [did]
    for base in bases:
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            p = os.path.join(CACHE_DIR, base + ext)
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
    tombstone = os.path.join(CACHE_DIR, did + ".none")
    if mark_cleared:
        try:
            with open(tombstone, "w", encoding="utf-8"):
                pass
        except OSError:
            pass
    else:
        try:
            os.remove(tombstone)
        except OSError:
            pass


def _image_ext_from_bytes(blob):
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(blob) >= 12 and blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return ".webp"
    return None


def _read_image_upload(file_obj, max_bytes):
    blob = file_obj.read(max_bytes + 1)
    if len(blob) > max_bytes:
        return None, "Image is too large."
    ext = _image_ext_from_bytes(blob)
    if not ext:
        return None, "Unsupported image type."
    return (blob, ext), None


def _public_ip(hostname):
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for info in infos:
        addr = info[4][0]
        # Strip IPv6 zone IDs (e.g. "fe80::1%eth0") before parsing; the scoped
        # portion is not part of the address and causes ipaddress to raise ValueError.
        if '%' in addr:
            addr = addr.split('%', 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False  # genuinely unparseable — block to be safe
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            return False
    return bool(infos)


def _safe_image_url(url):
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return False
    return _public_ip(parsed.hostname)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_image_url(newurl):
            raise ValueError("Unsafe redirect target")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_public_url(url, timeout=20):
    if not _safe_image_url(url):
        raise ValueError("Unsafe image URL")
    opener = urllib.request.build_opener(_SafeRedirectHandler)
    req = urllib.request.Request(url, headers={"User-Agent": REF_UA})
    return opener.open(req, timeout=timeout)
