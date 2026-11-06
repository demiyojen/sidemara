#!/usr/bin/env python3
"""Local contacts manager. Run: python server.py  (iCloud)  or  python server.py --demo"""
import argparse
import base64
import json
import os
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import vcard
from stores import CardDAVStore, ConflictError, FolderStore

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = threading.RLock()


def enc(href):
    return base64.urlsafe_b64encode(href.encode()).decode().rstrip("=")


def dec(i):
    return base64.urlsafe_b64decode(i + "=" * (-len(i) % 4)).decode()


class Service:
    def __init__(self, store):
        self.store = store
        self.items = {}  # href -> {"etag", "card"}
        self.reload(backup=True)

    def reload(self, backup=False):
        rows = self.store.list()
        self.items = {}
        for href, etag, text in rows:
            for c in vcard.split_cards(text)[:1]:
                self.items[href] = {"etag": etag, "card": vcard.Card.from_lines(c)}
        if backup:
            d = os.path.join(HERE, "backups")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, datetime.now().strftime("%Y%m%d-%H%M%S") + ".vcf")
            with open(p, "w", encoding="utf-8", newline="") as f:
                for href, etag, text in rows:
                    f.write(text if text.endswith("\n") else text + "\r\n")
            print(f"Yedek yazıldı: {p} ({len(rows)} kayıt)")

    def by_uid(self):
        return {v["card"].uid: h for h, v in self.items.items() if v["card"].uid}

    def groups_of(self):
        g = {}
        for h, v in self.items.items():
            if v["card"].is_group:
                for u in v["card"].members:
                    g.setdefault(u, []).append(enc(h))
        return g

    def summary(self, href, v, gmap):
        c = v["card"]
        return {"id": enc(href), "name": c.display_name(), "org": c.org(),
                "phones": [p["value"] for p in c.multi("TEL")],
                "emails": [e["value"] for e in c.multi("EMAIL")],
                "hasPhoto": c.get("PHOTO") is not None,
                "groups": gmap.get(c.uid, [])}

    def list(self):
        gmap = self.groups_of()
        contacts, groups = [], []
        for h, v in self.items.items():
            c = v["card"]
            if c.is_group:
                groups.append({"id": enc(h), "name": c.display_name(), "count": len(c.members)})
            else:
                contacts.append(self.summary(h, v, gmap))
        contacts.sort(key=lambda x: (x["name"] or "~").lower())
        groups.sort(key=lambda x: x["name"].lower())
        return {"contacts": contacts, "groups": groups}

    def detail(self, id):
        v = self.items[dec(id)]
        c = v["card"]
        d = {"id": id, "fn": c.display_name(), **c.name_parts(), "org": c.org(),
             "phones": c.multi("TEL"), "emails": c.multi("EMAIL"), "note": c.note(),
             "hasPhoto": c.get("PHOTO") is not None}
        return d

    def photo(self, id):
        return self.items[dec(id)]["card"].photo_bytes()

    def _save(self, href):
        v = self.items[href]
        v["etag"] = self.store.put(href, v["card"].serialize(), v["etag"]) or v["etag"]

    def save(self, d):
        photo = d.pop("photo", None)  # data URL, "" to remove, None to keep
        if d.get("id"):
            href = dec(d["id"])
            c = self.items[href]["card"]
            c.apply(d)
            self._apply_photo(c, photo)
            self._save(href)
            return d["id"]
        c = vcard.new_card(d)
        self._apply_photo(c, photo)
        href, etag = self.store.create(c.uid, c.serialize())
        self.items[href] = {"etag": etag, "card": c}
        return enc(href)

    @staticmethod
    def _apply_photo(c, photo):
        if photo is None:
            return
        if photo == "":
            c.set_photo(None)
        elif photo.startswith("data:"):
            head, _, b64 = photo.partition(",")
            c.set_photo(base64.b64decode(b64), head[5:].split(";")[0])

    def delete(self, ids):
        for i in ids:
            href = dec(i)
            v = self.items.get(href)
            if not v:
                continue
            uid = v["card"].uid
            self.store.delete(href, v["etag"])
            del self.items[href]
            if uid:  # drop from groups
                for gh, gv in list(self.items.items()):
                    if gv["card"].is_group and uid in gv["card"].members:
                        gv["card"].set_members([m for m in gv["card"].members if m != uid])
                        gv["card"].touch()
                        self._save(gh)

    def group_create(self, name):
        c = vcard.new_card(group_name=name.strip())
        href, etag = self.store.create(c.uid, c.serialize())
        self.items[href] = {"etag": etag, "card": c}
        return enc(href)

    def group_members(self, gid, add, remove):
        href = dec(gid)
        g = self.items[href]["card"]
        cur = g.members
        u = {self.items[dec(i)]["card"].uid for i in add}
        r = {self.items[dec(i)]["card"].uid for i in remove}
        new = [m for m in cur if m not in r] + [x for x in u if x and x not in cur]
        g.set_members(new)
        g.touch()
        self._save(href)

    def duplicates(self):
        by_phone, by_name = {}, {}
        for h, v in self.items.items():
            c = v["card"]
            if c.is_group:
                continue
            i = enc(h)
            for p in c.multi("TEL"):
                k = vcard.normalize_phone(p["value"])
                if len(k) >= 7:
                    by_phone.setdefault(k, set()).add(i)
            n = c.display_name().strip().lower()
            if n:
                by_name.setdefault(n, set()).add(i)
        # union-find on groups of 2+
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for grp in list(by_phone.values()) + list(by_name.values()):
            if len(grp) > 1:
                g = list(grp)
                for o in g[1:]:
                    parent[find(o)] = find(g[0])
        clusters = {}
        for x in list(parent):
            clusters.setdefault(find(x), []).append(x)
        gmap = self.groups_of()
        res = [[self.summary(dec(i), self.items[dec(i)], gmap) for i in ids]
               for ids in clusters.values() if len(ids) > 1]
        res.sort(key=lambda g: (g[0]["name"] or "").lower())
        return res

    def merge(self, keep, others):
        kh = dec(keep)
        k = self.items[kh]["card"]
        phones, emails = k.multi("TEL"), k.multi("EMAIL")
        seen_p = {vcard.normalize_phone(p["value"]) for p in phones}
        seen_e = {e["value"].lower() for e in emails}
        notes = [k.note()] if k.note() else []
        for o in others:
            oc = self.items[dec(o)]["card"]
            for p in oc.multi("TEL"):
                if vcard.normalize_phone(p["value"]) not in seen_p:
                    phones.append(p); seen_p.add(vcard.normalize_phone(p["value"]))
            for e in oc.multi("EMAIL"):
                if e["value"].lower() not in seen_e:
                    emails.append(e); seen_e.add(e["value"].lower())
            if oc.note() and oc.note() not in notes:
                notes.append(oc.note())
            if not k.org() and oc.org():
                k.set_single("ORG", vcard.escape(oc.org()))
            if not k.get("PHOTO") and oc.get("PHOTO"):
                k.lines.append(oc.get("PHOTO"))
        k.apply({"phones": phones, "emails": emails, "note": "\n".join(notes)})
        # move group memberships
        for gh, gv in self.items.items():
            g = gv["card"]
            if g.is_group:
                ouids = {self.items[dec(o)]["card"].uid for o in others}
                if ouids & set(g.members) and k.uid not in g.members:
                    g.set_members(g.members + [k.uid])
        self._save(kh)
        self.delete(others)


SVC = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _guard(self):
        # only the page served by this server may call the API (blocks other sites / DNS rebinding)
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self._send(403, {"error": "forbidden"}); return False
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            self._send(403, {"error": "forbidden"}); return False
        return True

    def do_GET(self):
        if not self._guard(): return
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            with LOCK:
                if u.path in ("/", "/index.html"):
                    with open(os.path.join(HERE, "static", "index.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if u.path == "/api/contacts":
                    return self._send(200, SVC.list())
                if u.path == "/api/contact":
                    return self._send(200, SVC.detail(q["id"][0]))
                if u.path == "/api/photo":
                    data, mime = SVC.photo(q["id"][0])
                    if not data: return self._send(404, b"", "text/plain")
                    return self._send(200, data, mime)
                if u.path == "/api/duplicates":
                    return self._send(200, SVC.duplicates())
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_POST(self):
        if not self._guard(): return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
            p = urlparse(self.path).path
            with LOCK:
                if p == "/api/save":
                    return self._send(200, {"id": SVC.save(d)})
                if p == "/api/delete":
                    if d.get("confirm") is not True:
                        return self._send(400, {"error": "confirm gerekli"})
                    SVC.delete(d["ids"]); return self._send(200, {"ok": True})
                if p == "/api/group/create":
                    return self._send(200, {"id": SVC.group_create(d["name"])})
                if p == "/api/group/members":
                    SVC.group_members(d["gid"], d.get("add", []), d.get("remove", []))
                    return self._send(200, {"ok": True})
                if p == "/api/merge":
                    SVC.merge(d["keep"], d["others"]); return self._send(200, {"ok": True})
                if p == "/api/reload":
                    SVC.reload(); return self._send(200, {"ok": True})
            self._send(404, {"error": "not found"})
        except ConflictError as e:
            self._send(409, {"error": str(e)})
        except Exception as e:
            self._send(500, {"error": str(e)})


def main():
    global SVC
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="iCloud yerine ./demo-data klasörünü kullan")
    ap.add_argument("--folder", help="iCloud yerine bu .vcf klasörünü kullan")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if a.demo or a.folder:
        store = FolderStore(a.folder or os.path.join(HERE, "demo-data"))
    else:
        user = os.environ.get("ICLOUD_APPLE_ID")
        pw = os.environ.get("ICLOUD_APP_PASSWORD")
        cfg = os.path.join(HERE, "config.json")
        if (not user or not pw) and os.path.exists(cfg):
            c = json.load(open(cfg, encoding="utf-8"))
            user, pw = c.get("apple_id"), c.get("app_password")
        if not user or not pw:
            sys.exit("config.json (apple_id, app_password) ya da ICLOUD_APPLE_ID / ICLOUD_APP_PASSWORD gerekli. README'ye bakın.")
        store = CardDAVStore(user, pw)
    SVC = Service(store)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print("Hazır:", url)
    if not a.no_browser:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
