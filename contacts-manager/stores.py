"""Storage backends: iCloud CardDAV and a local folder of .vcf files (demo/offline)."""
import base64
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET

import vcard

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:carddav"}


class Store:
    """Interface: list() -> [(href, etag, text)]; put/delete; create."""

    def list(self): raise NotImplementedError
    def put(self, href, text, etag): raise NotImplementedError
    def create(self, uid, text): raise NotImplementedError
    def delete(self, href, etag): raise NotImplementedError


class FolderStore(Store):
    def __init__(self, path):
        self.path = path
        os.makedirs(path, exist_ok=True)

    def _etag(self, p):
        st = os.stat(p)
        return "%d-%d" % (st.st_mtime_ns, st.st_size)

    def list(self):
        out = []
        for fn in sorted(os.listdir(self.path)):
            if not fn.lower().endswith(".vcf"):
                continue
            p = os.path.join(self.path, fn)
            with open(p, encoding="utf-8") as f:
                out.append((fn, self._etag(p), f.read()))
        return out

    def put(self, href, text, etag):
        p = os.path.join(self.path, os.path.basename(href))
        if etag and os.path.exists(p) and self._etag(p) != etag:
            raise ConflictError("Kayıt başka yerde değişmiş. Yeniden yükleyin.")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return self._etag(p)

    def create(self, uid, text):
        href = re.sub(r"[^A-Za-z0-9_-]", "", uid) + ".vcf"
        return href, self.put(href, text, None)

    def delete(self, href, etag):
        p = os.path.join(self.path, os.path.basename(href))
        if os.path.exists(p):
            os.remove(p)


class ConflictError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class CardDAVStore(Store):
    def __init__(self, user, password, base="https://contacts.icloud.com/"):
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.opener = urllib.request.build_opener(NoRedirect)
        self.base = base
        self.book = None

    def _req(self, method, url, body=None, headers=None, depth=None):
        h = {"Authorization": self.auth, "User-Agent": "contacts-manager/1.0"}
        if body is not None:
            h["Content-Type"] = "application/xml; charset=utf-8"
        if depth is not None:
            h["Depth"] = str(depth)
        h.update(headers or {})
        data = body.encode("utf-8") if isinstance(body, str) else body
        for _ in range(6):
            req = urllib.request.Request(url, data=data, method=method, headers=h)
            try:
                with self.opener.open(req, timeout=60) as r:
                    return r.status, r.read(), dict(r.headers), url
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 307, 308) and e.headers.get("Location"):
                    url = urllib.parse.urljoin(url, e.headers["Location"])
                    continue
                if e.code == 401:
                    raise PermissionError("iCloud girişi reddedildi (401). Apple ID ve uygulamaya özel parolayı kontrol edin.")
                if e.code == 412:
                    raise ConflictError("Kayıt başka yerde değişmiş. Yeniden yükleyin.")
                if e.code in (200, 201, 204, 207):
                    return e.code, e.read(), dict(e.headers), url
                raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {e.read()[:300]!r}")
        raise RuntimeError("Çok fazla yönlendirme")

    def _first_href(self, xml, path, base):
        root = ET.fromstring(xml)
        el = root.find(path, NS)
        return urllib.parse.urljoin(base, el.text.strip()) if el is not None and el.text else None

    def discover(self):
        if self.book:
            return self.book
        body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
        _, xml, _, url = self._req("PROPFIND", self.base, body, depth=0)
        principal = self._first_href(xml, ".//d:current-user-principal/d:href", url)
        if not principal:
            raise RuntimeError("iCloud principal bulunamadı")
        body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
                '<d:prop><c:addressbook-home-set/></d:prop></d:propfind>')
        _, xml, _, url = self._req("PROPFIND", principal, body, depth=0)
        home = self._first_href(xml, ".//c:addressbook-home-set/d:href", url)
        body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>')
        _, xml, _, url = self._req("PROPFIND", home, body, depth=1)
        root = ET.fromstring(xml)
        for r in root.findall("d:response", NS):
            if r.find(".//c:addressbook", NS) is not None:
                self.book = urllib.parse.urljoin(url, r.find("d:href", NS).text)
                return self.book
        raise RuntimeError("Adres defteri bulunamadı")

    def list(self):
        book = self.discover()
        body = ('<?xml version="1.0"?><c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
                '<d:prop><d:getetag/><c:address-data/></d:prop></c:addressbook-query>')
        _, xml, _, url = self._req("REPORT", book, body, depth=1)
        out = []
        for r in ET.fromstring(xml).findall("d:response", NS):
            href = r.find("d:href", NS).text
            etag = r.findtext(".//d:getetag", default="", namespaces=NS)
            data = r.findtext(".//c:address-data", default="", namespaces=NS)
            if data:
                out.append((urllib.parse.urljoin(url, href), etag, data))
        return out

    def put(self, href, text, etag):
        h = {"Content-Type": "text/vcard; charset=utf-8"}
        if etag:
            h["If-Match"] = etag
        _, _, hd, _ = self._req("PUT", href, text, headers=h)
        return hd.get("ETag", "") or hd.get("Etag", "")

    def create(self, uid, text):
        href = urllib.parse.urljoin(self.discover(), uuid.uuid4().hex.upper() + ".vcf")
        h = {"Content-Type": "text/vcard; charset=utf-8", "If-None-Match": "*"}
        _, _, hd, _ = self._req("PUT", href, text, headers=h)
        return href, hd.get("ETag", "") or hd.get("Etag", "")

    def delete(self, href, etag):
        h = {"If-Match": etag} if etag else {}
        self._req("DELETE", href, headers=h)
