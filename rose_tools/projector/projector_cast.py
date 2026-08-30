#!/usr/bin/env python3
"""Display an image or video on Noobia's HY300 HCCast projector."""
import argparse, http.server, ipaddress, re, shutil, socket, subprocess, tempfile, threading, time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen
import xml.etree.ElementTree as ET

PROJECTOR_MAC = "30:4a:26:07:94:26"
UUID_SUFFIX = "304a26079426"
SERVICE = "urn:schemas-upnp-org:service:AVTransport:1"
IMAGES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}

def local_ip(host):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((host, 9)); return sock.getsockname()[0]

def find_projector():
    network = ipaddress.ip_network(f"{local_ip('192.168.100.1')}/24", strict=False)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.setblocking(False)
        for address in network.hosts():
            try: probe.sendto(b"\0", (str(address), 9))
            except OSError: pass
    time.sleep(1.2)
    try: entries = Path("/proc/net/arp").read_text().splitlines()[1:]
    except OSError as error: raise RuntimeError(f"cannot read ARP table: {error}") from error
    for entry in entries:
        fields = entry.split()
        if len(fields) >= 4 and fields[3].lower() == PROJECTOR_MAC: return fields[0]
    raise RuntimeError(f"projector MAC {PROJECTOR_MAC} not found on {network}")

def discover(host):
    query = ('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: upnp:rootdevice\r\n\r\n').encode()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); sock.bind(("", 0)); sock.settimeout(.5)
        sock.sendto(query, ("239.255.255.250", 1900)); end = time.monotonic() + 6
        while time.monotonic() < end:
            try: data, address = sock.recvfrom(65535)
            except socket.timeout: continue
            text = data.decode(errors="replace")
            if address[0] == host and "HCCast" in text and UUID_SUFFIX in text.lower():
                match = re.search(r"(?im)^LOCATION:\s*(\S+)", text)
                if match: return match.group(1)
    fallback = f"http://{host}:49595/description.xml"
    try:
        with urlopen(fallback, timeout=3) as response:
            if b"Hccast-079426_dlna" in response.read(): return fallback
    except OSError: pass
    raise RuntimeError("Hccast-079426 DLNA renderer not found")

def get_control(description):
    root = ET.fromstring(urlopen(description, timeout=8).read()); ns = {"d": "urn:schemas-upnp-org:device-1-0"}
    name = root.findtext(".//d:friendlyName", namespaces=ns)
    if name != "Hccast-079426_dlna": raise RuntimeError(f"unexpected renderer: {name}")
    for item in root.findall(".//d:service", ns):
        if item.findtext("d:serviceType", namespaces=ns) == SERVICE:
            return urljoin(description, item.findtext("d:controlURL", namespaces=ns))
    raise RuntimeError("AVTransport endpoint missing")

def soap(control, action, inner=""):
    url = urlsplit(control)
    body = (f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:{action} xmlns:u="{SERVICE}"><InstanceID>0</InstanceID>{inner}</u:{action}></s:Body></s:Envelope>').encode()
    head = (f"POST {url.path} HTTP/1.1\r\nHost: {url.hostname}:{url.port}\r\nContent-Type: text/xml; charset=\"utf-8\"\r\nSOAPACTION: \"{SERVICE}#{action}\"\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()
    with socket.create_connection((url.hostname, url.port or 80), timeout=8) as connection:
        connection.settimeout(8); connection.sendall(head + body); connection.shutdown(socket.SHUT_WR); response = b""
        while True:
            try: chunk = connection.recv(8192)
            except socket.timeout: break
            if not chunk: break
            response += chunk
    status = response.split(b"\r\n", 1)[0].decode(errors="replace")
    if " 200 " not in status: raise RuntimeError(f"DLNA {action} failed: {status or 'no response'}")

def ffmpeg(arguments):
    if not shutil.which("ffmpeg"): raise RuntimeError("ffmpeg is required")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *arguments], check=True)

def prepare(source, folder):
    video_filter = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black"
    if source.suffix.lower() in IMAGES:
        output = folder / "projector-image.jpg"; ffmpeg(["-i", str(source), "-vf", video_filter, "-q:v", "2", str(output)]); return output, True
    output = folder / "projector-video.mp4"
    ffmpeg(["-i", str(source), "-vf", video_filter, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(output)])
    return output, False

class Handler(http.server.SimpleHTTPRequestHandler):
    fetched = threading.Event()
    def do_GET(self): self.fetched.set(); super().do_GET()
    def log_message(self, *args): pass

def duration(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True)
    return float(result.stdout.strip())

def cast(source, host):
    control = get_control(discover(host))
    with tempfile.TemporaryDirectory(prefix="rose-projector-") as temporary:
        folder = Path(temporary); media, image = prepare(source, folder); bind = local_ip(host)
        factory = lambda *args, **kwargs: Handler(*args, directory=str(folder), **kwargs)
        server = http.server.ThreadingHTTPServer((bind, 0), factory); threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            Handler.fetched.clear(); media_url = f"http://{bind}:{server.server_port}/{media.name}"
            try: soap(control, "Pause")
            except RuntimeError: pass
            soap(control, "SetAVTransportURI", f"<CurrentURI>{media_url}</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>")
            soap(control, "Play", "<Speed>1</Speed>")
            if not Handler.fetched.wait(10): raise RuntimeError("projector did not fetch the media")
            print(f"Displaying {source.name} on Hccast-079426 via DLNA")
            if not image: time.sleep(duration(media) + 5)
        finally: server.shutdown(); server.server_close()

def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("media", type=Path); parser.add_argument("--host")
    arguments = parser.parse_args(); source = arguments.media.expanduser().resolve()
    if not source.is_file(): raise SystemExit(f"Media file not found: {source}")
    try: cast(source, arguments.host or find_projector())
    except Exception as error: raise SystemExit(str(error)) from None

if __name__ == "__main__": main()
