"""Minimal vCard 3.0 parser/serializer that preserves unknown lines."""
import base64
import re
import uuid
from datetime import datetime, timezone


class Line:
    __slots__ = ("group", "name", "params", "value")

    def __init__(self, group, name, params, value):
        self.group, self.name, self.params, self.value = group, name, params, value

    def serialize(self):
        head = (self.group + "." if self.group else "") + self.name
        if self.params:
            head += ";" + self.params
        return fold(head + ":" + self.value)


def fold(line, width=75):
    b = line.encode("utf-8")
    if len(b) <= width:
        return line
    out, cur = [], b""
    for ch in line:
        cb = ch.encode("utf-8")
        limit = width if not out else width - 1
        if len(cur) + len(cb) > limit:
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += cb
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def unfold(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for ln in text.split("\n"):
        if ln[:1] in (" ", "\t") and out:
            out[-1] += ln[1:]
        else:
            out.append(ln)
    return [l for l in out if l.strip()]


def split_cards(text):
    """Split a text with several BEGIN:VCARD..END:VCARD blocks."""
    cards, cur = [], None
    for ln in unfold(text):
        u = ln.upper()
        if u == "BEGIN:VCARD":
            cur = []
        elif u == "END:VCARD":
            if cur is not None:
                cards.append(cur)
            cur = None
        elif cur is not None:
            cur.append(ln)
    return cards


def parse_line(ln):
    in_q, idx = False, -1
    for i, c in enumerate(ln):
        if c == '"':
            in_q = not in_q
        elif c == ":" and not in_q:
            idx = i
            break
    if idx < 0:
        return None
    head, value = ln[:idx], ln[idx + 1:]
    parts = head.split(";", 1)
    nameg = parts[0]
    params = parts[1] if len(parts) > 1 else ""
    group = ""
    if "." in nameg:
        group, nameg = nameg.split(".", 1)
    return Line(group, nameg.upper(), params, value)


def unescape(v):
    return (v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def escape(v):
    return (v.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,")
            .replace(";", "\\;"))


def split_semis(v):
    parts, cur, i = [], "", 0
    while i < len(v):
        if v[i] == "\\" and i + 1 < len(v):
            cur += v[i:i + 2]
            i += 2
            continue
        if v[i] == ";":
            parts.append(cur)
            cur = ""
        else:
            cur += v[i]
        i += 1
    parts.append(cur)
    return [unescape(p) for p in parts]


def type_of(params):
    types = []
    for p in params.split(";"):
        if not p:
            continue
        k, _, v = p.partition("=")
        if not _:
            types.append(p.lower())
        elif k.upper() == "TYPE":
            types += [t.strip('"').lower() for t in v.split(",")]
    for t in types:
        if t not in ("voice", "pref", "internet"):
            return t
    return types[0] if types else ""


class Card:
    def __init__(self, lines=None):
        self.lines = lines or []

    @classmethod
    def from_lines(cls, raw_lines):
        return cls([l for l in (parse_line(x) for x in raw_lines) if l])

    @classmethod
    def parse(cls, text):
        cards = split_cards(text)
        return cls.from_lines(cards[0]) if cards else cls()

    def serialize(self):
        body = [l.serialize() for l in self.lines if l.name not in ("BEGIN", "END")]
        return "\r\n".join(["BEGIN:VCARD"] + body + ["END:VCARD"]) + "\r\n"

    def get(self, name):
        for l in self.lines:
            if l.name == name:
                return l
        return None

    def all(self, name):
        return [l for l in self.lines if l.name == name]

    def set_single(self, name, value, params=""):
        l = self.get(name)
        if value in (None, ""):
            if l:
                self.lines.remove(l)
            return
        if l:
            l.value = value
        else:
            self.lines.append(Line("", name, params, value))

    @property
    def uid(self):
        l = self.get("UID")
        return l.value if l else ""

    @property
    def is_group(self):
        l = self.get("X-ADDRESSBOOKSERVER-KIND")
        return bool(l and l.value.lower() == "group")

    @property
    def members(self):
        return [l.value.replace("urn:uuid:", "") for l in self.all("X-ADDRESSBOOKSERVER-MEMBER")]

    def set_members(self, uids):
        self.lines = [l for l in self.lines if l.name != "X-ADDRESSBOOKSERVER-MEMBER"]
        for u in uids:
            self.lines.append(Line("", "X-ADDRESSBOOKSERVER-MEMBER", "", "urn:uuid:" + u))

    def name_parts(self):
        l = self.get("N")
        p = split_semis(l.value) if l else []
        p += [""] * (5 - len(p))
        return {"last": p[0], "first": p[1], "middle": p[2], "prefix": p[3], "suffix": p[4]}

    def display_name(self):
        l = self.get("FN")
        fn = unescape(l.value).strip() if l else ""
        if fn:
            return fn
        n = self.name_parts()
        s = " ".join(x for x in (n["prefix"], n["first"], n["middle"], n["last"], n["suffix"]) if x)
        if s:
            return s
        org = self.org()
        return org

    def org(self):
        l = self.get("ORG")
        return " ".join(x for x in split_semis(l.value) if x) if l else ""

    def multi(self, name):
        return [{"type": type_of(l.params), "value": unescape(l.value)} for l in self.all(name)]

    def set_multi(self, name, items):
        dropped = {l.group for l in self.all(name) if l.group}
        self.lines = [l for l in self.lines if l.name != name]
        self.lines = [l for l in self.lines if not (l.group in dropped and l.name == "X-ABLABEL")]
        for it in items:
            v = (it.get("value") or "").strip()
            if not v:
                continue
            t = (it.get("type") or "").strip().lower()
            params = ("type=" + t) if t else ""
            self.lines.append(Line("", name, params, escape(v) if name != "TEL" else v))

    def note(self):
        l = self.get("NOTE")
        return unescape(l.value) if l else ""

    def photo_bytes(self):
        l = self.get("PHOTO")
        if not l:
            return None, None
        p = l.params.upper()
        if "ENCODING=B" in p or "ENCODING=BASE64" in p or p.endswith(";B") or p == "B":
            try:
                data = base64.b64decode(l.value)
            except Exception:
                return None, None
            mime = "image/png" if "PNG" in p else "image/jpeg"
            if data[:4] == b"\x89PNG":
                mime = "image/png"
            return data, mime
        if l.value.startswith("data:"):
            head, _, b64 = l.value.partition(",")
            try:
                return base64.b64decode(b64), head[5:].split(";")[0]
            except Exception:
                return None, None
        return None, None

    def set_photo(self, data, mime="image/jpeg"):
        self.lines = [l for l in self.lines if l.name != "PHOTO"]
        if data:
            typ = "PNG" if "png" in mime else "JPEG"
            self.lines.append(Line("", "PHOTO", "ENCODING=b;TYPE=" + typ, base64.b64encode(data).decode()))

    def touch(self):
        self.set_single("REV", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def apply(self, d):
        """Apply API dict (first/last/org/phones/emails/note...) to the card."""
        n = self.name_parts()
        for k in ("first", "last", "middle", "prefix", "suffix"):
            if k in d:
                n[k] = (d[k] or "").strip()
        self.set_single("N", ";".join(escape(n[k]) for k in ("last", "first", "middle", "prefix", "suffix")))
        if "fn" in d:
            fn = (d["fn"] or "").strip()
        else:
            fn = ""
        if not fn:
            fn = " ".join(x for x in (n["prefix"], n["first"], n["middle"], n["last"], n["suffix"]) if x)
        if not fn:
            fn = (d.get("org") or self.org() or "").strip()
        self.set_single("FN", escape(fn))
        if "org" in d:
            self.set_single("ORG", escape((d["org"] or "").strip()))
        if "phones" in d:
            self.set_multi("TEL", d["phones"])
        if "emails" in d:
            self.set_multi("EMAIL", d["emails"])
        if "note" in d:
            self.set_single("NOTE", escape(d["note"] or ""))
        self.touch()


def new_card(d=None, group_name=None):
    c = Card()
    c.lines.append(Line("", "VERSION", "", "3.0"))
    c.lines.append(Line("", "PRODID", "", "-//contacts-manager//EN"))
    c.lines.append(Line("", "UID", "", str(uuid.uuid4()).upper()))
    if group_name:
        c.set_single("FN", escape(group_name))
        c.set_single("N", escape(group_name) + ";;;;")
        c.lines.append(Line("", "X-ADDRESSBOOKSERVER-KIND", "", "group"))
        c.touch()
    else:
        c.apply(d or {})
    return c


def normalize_phone(p):
    digits = re.sub(r"\D", "", p)
    return digits[-10:] if len(digits) >= 7 else digits
