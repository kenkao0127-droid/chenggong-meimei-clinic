"""Validate the clinic static site and optionally create an allowlisted publish artifact."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import argparse
import re
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'index.html', '.nojekyll'}
PERSONAL_SITE = 'https://kenkao0127-droid.github.io/dr-kao-personal-website/'
CLINIC_SITE = 'https://www.cm166.com.tw/'
GENERAL_MEDICINE = '腹痛、腸胃炎、感冒、發燒、高血壓、糖尿病、高血脂，以及痛風、代謝症候群、肥胖等慢性病治療'
DOCTOR_PHOTOS = (('陳炳諴', 'assets/images/doctor-chen.webp'), ('張峻愷', 'assets/images/doctor-chang.webp'), ('高傳紘', 'assets/images/doctor-kao.webp'))
QR_IMAGE = 'assets/images/line-qr.png'
MAX_PHOTO_BYTES = 150_000
BANNED_TEXT = ('第一名', '良醫健康網', '名醫', '最佳診所', '最好的', '保證', '根治', '@174kjvzv', '@cm166', 'lin.ee/Wjt5Hny', '限複診', '目前無線上預約功能')
CHEN_SOURCE = 'https://www.cm166.com.tw/archives/team/doctor01'
CHEN_REVIEW_CREDENTIAL = '<li>商業周刊《良醫健康網》獲得「胃腸肝膽科」第一名好醫師的評價</li>'


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Site(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.anchors = []
        self.assets = set()
        self.images = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            self.ids.append(a['id'])
        if tag == 'a':
            self.anchors.append(a)
        if tag == 'img' and a.get('src'):
            require(a.get('alt'), 'Image alt text is required')
            require(a.get('width') and a.get('height'), 'Declare intrinsic image dimensions')
            self.images.append(a['src'])
        for key in ('src',):
            if a.get(key):
                self.assets.add(a[key])
        if tag == 'link' and a.get('rel') == 'stylesheet' and not a['href'].startswith('https://'):
            self.assets.add(a['href'])


def publication_source(relative, *, allow_root_files=False):
    parts = relative.split('/')
    root_file = allow_root_files and relative in ROOT_FILES
    # Accept canonical, portable relative URL paths only; never normalize them.
    if (not root_file and (len(parts) < 2 or parts[0] != 'assets')) or any(
        part in {'', '.', '..'}
        or part.endswith((' ', '.'))
        or re.search(r'[\\<>:"|?*%#\x00-\x1f\x7f]', part)
        or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?: *\..*)?', part, re.I)
        for part in parts
    ):
        raise ValueError(f'Invalid publication path: {relative}')
    source = ROOT.joinpath(*parts)
    current = ROOT
    for part in parts:
        current = current / part
        if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
            raise ValueError(f'Missing or unsafe publication file: {relative}')
    boundary = ROOT.resolve() if root_file else (ROOT / 'assets').resolve()
    if not source.resolve().is_relative_to(boundary):
        raise ValueError(f'Invalid publication path: {relative}')
    if not source.is_file():
        raise ValueError(f'Missing or unsafe publication file: {relative}')
    return source


def validate():
    html = publication_source('index.html', allow_root_files=True).read_text(encoding='utf-8')
    publication_source('.nojekyll', allow_root_files=True)
    p = Site()
    p.feed(html)
    require(not [k for k, n in Counter(p.ids).items() if n > 1], 'Duplicate element IDs')
    for anchor in p.anchors:
        href = anchor['href']
        if href.startswith('#'):
            require(href[1:] in p.ids, f'Broken section link: {href}')
        elif href.startswith('https://'):
            if anchor.get('target') == '_blank':
                require('noopener' in anchor.get('rel', '').split(), 'External link needs noopener')
        else:
            require(re.fullmatch(r'tel:\+[0-9]+', href), 'Only HTTPS and valid telephone links are permitted')
    for asset in p.assets:
        publication_source(asset)
    expected = {
        CLINIC_SITE, PERSONAL_SITE,
        'https://lin.ee/Q2s1RMM', 'https://maps.app.goo.gl/L5pGWgFMGXgheZHG8',
        'tel:+8866' + '2215289',
    }
    require(expected.issubset({a['href'] for a in p.anchors}), 'Missing required clinic links')
    for anchor in p.anchors:
        if 'kenkao0127' in anchor['href']:
            require(anchor['href'] == PERSONAL_SITE, 'Only the doctor personal-home link may point to the personal site')
    live = re.sub(r'<!--.*?-->', '', html, flags=re.S)  # ignore HTML comments
    require('rel="canonical"' not in live and 'og:url' not in live and 'og:image"' not in live,
            'Do not claim the personal-site canonical/og URLs')
    require(p.images == [photo for _, photo in DOCTOR_PHOTOS] + [QR_IMAGE],
            'Images must be exactly three doctor photos (陳, 張, 高, in that order) followed by the LINE QR')
    sizes = set()
    for name, photo in DOCTOR_PHOTOS:
        data = publication_source(photo).read_bytes()
        require(data[:4] == b'RIFF' and data[8:12] == b'WEBP', f'Doctor photo must be WebP: {photo}')
        require(len(data) <= MAX_PHOTO_BYTES, f'Doctor photo too large: {photo}')
        require(b'EXIF' not in data and b'XMP ' not in data and b'ICCP' not in data, f'Doctor photo must have no metadata: {photo}')
    for name, photo in DOCTOR_PHOTOS:
        tag = re.search(r'<img[^>]*src="' + re.escape(photo) + r'"[^>]*>', html).group()
        require(f'alt="{name}醫師"' in tag, f'Photo alt text must be {name}醫師')
        dims = (re.search(r'width="(\d+)"', tag).group(1), re.search(r'height="(\d+)"', tag).group(1))
        sizes.add(dims)
    require(len(sizes) == 1, 'All doctor photos must share the same width/height')
    # The requested source-backed historical review belongs only to Dr. Chen's
    # credentials. Keep the general ban on rankings and promotional claims.
    claims = live
    chen_card = next((card for card in re.findall(r'<article class="doctor-card">.*?</article>', live, re.S)
                      if '<h3>陳炳諴 ' in card), '')
    if CHEN_REVIEW_CREDENTIAL in chen_card:
        credential_parser = Site()
        credential_parser.feed(chen_card)
        require(any(a['href'] == CHEN_SOURCE for a in credential_parser.anchors),
                'Dr. Chen review credential requires its source link')
        claims = claims.replace(chen_card, chen_card.replace(CHEN_REVIEW_CREDENTIAL, '', 1), 1)
    for word in BANNED_TEXT:
        require(word not in claims, f'Banned text found: {word}')
    require(live.count(GENERAL_MEDICINE) == 2, 'General medicine list must appear exactly twice (hero card and care box)')
    about = re.search(r'<section[^>]+id="about".*?</section>', live, re.S).group()
    require(CLINIC_SITE not in about, 'The 永康 site link must not appear in the about section')
    require(sum(a['href'] == CLINIC_SITE for a in p.anchors) == 3, 'Expected exactly three 永康 site links (intro strip, doctors, footer)')
    cards = re.findall(r'<article class="doctor-card">.*?</article>', html, re.S)
    require(len(cards) == 3, 'Expected exactly three doctor cards')
    for name in ('陳炳諴', '張峻愷', '高傳紘'):
        require(sum(name in card for card in cards) == 1, f'Missing doctor card: {name}')
    for card, (name, photo) in zip(cards, DOCTOR_PHOTOS):
        require(f'<h3>{name} ' in card and photo in card, f'Doctor card order/photo mismatch: expected {name} with {photo}')
    require('內科／胸腔內科' in html, 'Dr. Kao must be listed as internal medicine / pulmonary medicine')
    require(re.search(r'內視鏡檢查[^<]*<span class="badge">籌備中</span>', html), 'Endoscopy must be marked as in preparation')
    data = publication_source('assets/images/line-qr.png').read_bytes()
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'LINE QR bitmap must be PNG')
    width, height = struct.unpack('>II', data[16:24])
    require(width == height, 'LINE QR bitmap must remain square')
    print(f'PASS: {len(p.ids)} IDs; {len(p.assets)} local assets; 3 doctor cards; clinic links; square QR')
    return {'index.html', '.nojekyll', *p.assets}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path)
    args = parser.parse_args()
    files = validate()
    if args.build:
        require(
            not args.build.is_symlink() and not getattr(args.build, 'is_junction', lambda: False)(),
            'Build into a fresh directory',
        )
        target = args.build.resolve()
        require(not target.exists(), 'Build into a fresh directory')
        require(not target.is_relative_to((ROOT / 'assets').resolve()), 'Do not overwrite source assets')
        target.mkdir(parents=True)
        for rel in sorted(files):
            source = publication_source(rel, allow_root_files=True)
            destination = target / rel
            require(destination.resolve().is_relative_to(target), f'Invalid publication destination: {rel}')
            for current in (destination, *destination.parents):
                require(
                    not current.is_symlink() and not getattr(current, 'is_junction', lambda: False)(),
                    f'Unsafe publication destination: {rel}',
                )
                if current == target:
                    break
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        print(f'PASS: allowlisted publish artifact contains {len(files)} files')


if __name__ == '__main__':
    main()
