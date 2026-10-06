"""Regression tests for the clinic site publication boundary and content rules (stdlib only)."""
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import shutil
import struct
import subprocess
import sys
import unittest

from scripts import validate_site


class PublicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        scratch = os.environ.get('TMPDIR')
        self.temporary = TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repository'
        self.root.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(validate_site, 'ROOT', self.root).start()
        photos = {'陳炳諴': 'doctor-chen.webp', '張峻愷': 'doctor-chang.webp', '高傳紘': 'doctor-kao.webp'}
        images = ['line-qr.png', *photos.values()]
        self.assets = {'assets/site.css', 'assets/site.js'}
        self.assets.update(f'assets/images/{name}' for name in images)
        for relative in self.assets:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'RIFF\x04\0\0\0WEBPVP8 ' if path.suffix == '.webp' else b'fixture asset')
        (self.root / 'assets/images/line-qr.png').write_bytes(
            b'\x89PNG\r\n\x1a\n' + b'\0' * 8 + struct.pack('>II', 10, 10)
        )
        links = [
            'https://www.cm166.com.tw/', 'https://www.cm166.com.tw/', 'https://www.cm166.com.tw/', 'https://kenkao0127-droid.github.io/dr-kao-personal-website/',
            'https://lin.ee/Q2s1RMM', 'https://maps.app.goo.gl/L5pGWgFMGXgheZHG8',
            'tel:+8866' + '2215289',
        ]
        self.html = '<link rel="stylesheet" href="assets/site.css">'
        self.html += '<script src="assets/site.js"></script>'
        self.html += ''.join(f'<a href="{href}">contact</a>' for href in links)
        self.html += '<section id="about">about</section>'
        self.html += ''.join(
            f'<article class="doctor-card"><figure><img src="assets/images/{photos[name]}" width="900" height="675" alt="{name}醫師"></figure>'
            f'<h3>{name} <span>醫師</span></h3>{role}</article>'
            for name, role in (('陳炳諴', '內科'), ('張峻愷', '內科'), ('高傳紘', '內科／胸腔內科'))
        )
        self.html += '<small>' + validate_site.GENERAL_MEDICINE + '</small><p>' + validate_site.GENERAL_MEDICINE + '。</p>'
        self.html += '<li>內視鏡檢查<span class="badge">籌備中</span></li>'
        self.html += '<img src="assets/images/line-qr.png" alt="fixture" width="10" height="10">'
        (self.root / 'index.html').write_text(self.html, encoding='utf-8')
        (self.root / '.nojekyll').write_text('', encoding='utf-8')
        (self.root / 'README.md').write_text('private repository document', encoding='utf-8')

    def validate(self):
        with redirect_stdout(StringIO()):
            return validate_site.validate()

    def add_reference(self, relative):
        (self.root / 'index.html').write_text(
            self.html + f'<script src="{relative}"></script>', encoding='utf-8'
        )

    def test_parent_traversal_cannot_publish_repository_document(self):
        self.add_reference('assets/../README.md')
        with self.assertRaisesRegex(ValueError, 'Invalid publication path'):
            self.validate()

    def test_noncanonical_and_windows_ambiguous_paths_are_rejected(self):
        invalid = [
            'assets/images/../../README.md', 'assets/../assets/site.js',
            'assets/./site.js', 'assets//site.js', 'assets/',
            '/assets/site.js', str(self.root / 'assets/site.js'),
            'C:/assets/site.js', 'C:assets/site.js', '//server/share/site.js',
            r'assets\images\line-qr.png', r'assets/images\line-qr.png',
            r'assets/..\README.md', r'\assets\site.js',
            r'\\server\share\site.js', r'\\?\C:\assets\site.js',
            'assets/site.js:stream', 'assets/site.js.', 'assets/site.js ',
            'assets/CON', 'assets/nul.txt', 'assets/COM1.js', 'assets/LPT9.txt',
            'assets/con .js', 'assets/LPT1 .txt',
            'assets/site.js?query', 'assets/site.js#fragment',
            'assets/%2e%2e/README.md', 'assets/site\x00.js', 'assets/site\n.js',
        ]
        for relative in invalid:
            with self.subTest(relative=relative):
                self.add_reference(relative)
                with self.assertRaisesRegex(ValueError, 'Invalid publication path'):
                    self.validate()

    @contextmanager
    def symbolic_link(self, link, source):
        """Exercise real symlinks when permitted; report the Windows fallback."""
        try:
            link.symlink_to(source, target_is_directory=source.is_dir())
        except OSError as error:
            print(f'Symlink privilege unavailable; using is_symlink mock: {error}', file=sys.stderr)
            if source.is_dir():
                shutil.copytree(source, link)
            elif source.is_file():
                shutil.copyfile(source, link)
            original = Path.is_symlink
            with patch.object(Path, 'is_symlink', lambda path: path == link or original(path)):
                yield
        else:
            yield

    def test_symbolic_link_asset_file_is_rejected(self):
        link = self.root / 'assets/alias.js'
        self.add_reference('assets/alias.js')
        with self.symbolic_link(link, self.root / 'assets/site.js'):
            with self.assertRaisesRegex(ValueError, 'Missing or unsafe publication file'):
                self.validate()

    def test_symbolic_link_asset_ancestor_is_rejected(self):
        link = self.root / 'assets/alias'
        self.add_reference('assets/alias/line-qr.png')
        with self.symbolic_link(link, self.root / 'assets/images'):
            with self.assertRaisesRegex(ValueError, 'Missing or unsafe publication file'):
                self.validate()

    def test_symbolic_link_assets_directory_is_rejected(self):
        source = self.root / 'stored-assets'
        (self.root / 'assets').rename(source)
        with self.symbolic_link(self.root / 'assets', source):
            with self.assertRaisesRegex(ValueError, 'Missing or unsafe publication file'):
                self.validate()

    def test_symbolic_link_root_publication_files_are_rejected(self):
        for relative in ('index.html', '.nojekyll'):
            with self.subTest(relative=relative):
                link = self.root / relative
                source = self.root / f'{relative}.original'
                link.rename(source)
                try:
                    with self.symbolic_link(link, source):
                        with self.assertRaisesRegex(ValueError, 'Missing or unsafe publication file'):
                            self.validate()
                finally:
                    link.unlink()
                    source.rename(link)

    def test_missing_publication_files_are_rejected(self):
        for relative in ('assets/site.js', 'index.html', '.nojekyll'):
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaisesRegex(ValueError, 'Missing or unsafe publication file'):
                        self.validate()
                finally:
                    path.write_bytes(original)

    def test_directory_cannot_be_published_as_file(self):
        self.add_reference('assets/images')
        with self.assertRaisesRegex(ValueError, 'Missing or unsafe publication file'):
            self.validate()

    def test_resolved_asset_cannot_leave_assets_boundary(self):
        original = Path.resolve
        asset = self.root / 'assets/site.js'
        with patch.object(
            Path, 'resolve',
            lambda path, *args, **kwargs: self.root / 'README.md' if path == asset
            else original(path, *args, **kwargs),
        ):
            with self.assertRaisesRegex(ValueError, 'Invalid publication path'):
                self.validate()

    def test_validated_file_set_is_exact_allowlist(self):
        (self.root / 'assets/unreferenced.txt').write_text('not public', encoding='utf-8')
        self.assertEqual(self.validate(), {'index.html', '.nojekyll'} | self.assets)

    def build(self, target):
        with patch.object(sys, 'argv', ['validate_site.py', '--build', str(target)]):
            with redirect_stdout(StringIO()):
                validate_site.main()

    def test_build_revalidates_publication_paths(self):
        invalid = [
            'assets/../README.md', 'README.md', 'index.html/extra',
            str(self.root / 'README.md'), '/README.md', r'assets/images\line-qr.png',
        ]
        for number, relative in enumerate(invalid):
            with self.subTest(relative=relative):
                target = Path(self.temporary.name) / f'published-{number}'
                with patch.object(validate_site, 'validate', return_value={relative}):
                    with self.assertRaisesRegex(ValueError, 'Invalid publication path'):
                        self.build(target)
                self.assertFalse((target / 'README.md').exists())

    def test_resolved_destination_cannot_leave_output_directory(self):
        target = Path(self.temporary.name) / 'published'
        escaped = Path(self.temporary.name) / 'escaped.js'
        destination = target / 'assets/site.js'
        original = Path.resolve
        with patch.object(
            Path, 'resolve',
            lambda path, *args, **kwargs: escaped if path == destination
            else original(path, *args, **kwargs),
        ):
            with self.assertRaisesRegex(ValueError, 'Invalid publication destination'):
                self.build(target)
        self.assertFalse(escaped.exists())
        self.assertFalse(destination.exists())

    def test_symbolic_link_destination_ancestor_is_rejected(self):
        target = Path(self.temporary.name) / 'published'
        original = Path.is_symlink
        # Simulate metadata changing after the fresh output directory is created.
        with patch.object(
            Path, 'is_symlink',
            lambda path: path == target / 'assets' or original(path),
        ):
            with self.assertRaisesRegex(ValueError, 'Unsafe publication destination'):
                self.build(target)
        self.assertFalse((target / 'assets/site.js').exists())

    def test_symbolic_link_destination_file_is_rejected(self):
        target = Path(self.temporary.name) / 'published'
        original = Path.is_symlink
        with patch.object(
            Path, 'is_symlink',
            lambda path: path == target / '.nojekyll' or original(path),
        ):
            with self.assertRaisesRegex(ValueError, 'Unsafe publication destination'):
                self.build(target)
        self.assertFalse((target / '.nojekyll').exists())

    def test_dangling_symbolic_link_asset_is_rejected(self):
        link = self.root / 'assets/dangling.js'
        self.add_reference('assets/dangling.js')
        with self.symbolic_link(link, self.root / 'absent.js'):
            with self.assertRaisesRegex(ValueError, 'Missing or unsafe publication file'):
                self.validate()

    def test_dangling_symbolic_link_output_is_rejected(self):
        target = Path(self.temporary.name) / 'published'
        missing = Path(self.temporary.name) / 'absent-output'
        with self.symbolic_link(target, missing):
            with self.assertRaisesRegex(ValueError, 'Build into a fresh directory'):
                self.build(target)
        self.assertFalse(missing.exists())

    def test_only_explicit_root_files_are_allowed(self):
        for relative in ('index.html', '.nojekyll'):
            with self.subTest(relative=relative):
                self.assertEqual(
                    validate_site.publication_source(relative, allow_root_files=True),
                    self.root / relative,
                )
                self.add_reference(relative)
                with self.assertRaisesRegex(ValueError, 'Invalid publication path'):
                    self.validate()
        with self.assertRaisesRegex(ValueError, 'Invalid publication path'):
            validate_site.publication_source('README.md', allow_root_files=True)

    def test_built_file_set_and_contents_are_exact(self):
        (self.root / 'assets/unreferenced.txt').write_text('not public', encoding='utf-8')
        (self.root / 'content').mkdir()
        (self.root / 'content/private.md').write_text('not public', encoding='utf-8')
        target = Path(self.temporary.name) / 'published'
        self.build(target)
        actual = {
            path.relative_to(target).as_posix()
            for path in target.rglob('*') if path.is_file()
        }
        self.assertEqual(actual, {'index.html', '.nojekyll'} | self.assets)
        for relative in actual:
            with self.subTest(relative=relative):
                self.assertEqual((target / relative).read_bytes(), (self.root / relative).read_bytes())

    def test_real_site_cli_publishes_exact_file_set(self):
        project = Path(validate_site.__file__).resolve().parents[1]
        target = Path(self.temporary.name) / 'real-site'
        result = subprocess.run(
            [sys.executable, '-B', str(project / 'scripts/validate_site.py'), '--build', str(target)],
            cwd=project, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        expected = {
            'index.html', '.nojekyll', 'assets/site.css', 'assets/site.js',
            'assets/images/line-qr.png', 'assets/images/doctor-chen.webp',
            'assets/images/doctor-chang.webp', 'assets/images/doctor-kao.webp',
        }
        actual = {
            path.relative_to(target).as_posix()
            for path in target.rglob('*') if path.is_file()
        }
        self.assertEqual(actual, expected)
        for relative in actual:
            with self.subTest(relative=relative):
                self.assertEqual((target / relative).read_bytes(), (project / relative).read_bytes())

    def test_existing_output_is_rejected(self):
        target = Path(self.temporary.name) / 'published'
        target.mkdir()
        marker = target / 'untouched.txt'
        marker.write_text('original', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Build into a fresh directory'):
            self.build(target)
        self.assertEqual(marker.read_text(encoding='utf-8'), 'original')

    def test_output_inside_source_assets_is_rejected(self):
        target = self.root / 'assets/published'
        with self.assertRaisesRegex(ValueError, 'Do not overwrite source assets'):
            self.build(target)
        self.assertFalse(target.exists())

    def test_unsafe_link_is_rejected_under_optimization(self):
        (self.root / 'index.html').write_text(
            self.html + '<a href="http://example.com">unsafe link</a>', encoding='utf-8'
        )
        result = subprocess.run(
            [sys.executable, '-B', '-O', '-c',
             'from pathlib import Path; import sys; from scripts import validate_site; '
             'validate_site.ROOT = Path(sys.argv[1]); validate_site.validate()', str(self.root)],
            cwd=Path(validate_site.__file__).resolve().parents[1],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('Only HTTPS and valid telephone links are permitted', result.stderr)

    def write_html(self, html):
        (self.root / 'index.html').write_text(html, encoding='utf-8')

    def test_personal_photos_are_rejected(self):
        (self.root / 'assets/images/portrait.png').write_bytes(b'fixture asset')
        self.write_html(self.html + '<img src="assets/images/portrait.png" alt="x" width="1" height="1">')
        with self.assertRaisesRegex(ValueError, 'Images must be exactly'):
            self.validate()

    def test_ranking_claims_are_rejected(self):
        self.write_html(self.html + '<p>良醫健康網第一名</p>')
        with self.assertRaisesRegex(ValueError, 'Banned text found'):
            self.validate()

    def test_source_backed_chen_review_credential_is_allowed(self):
        credential = (validate_site.CHEN_REVIEW_CREDENTIAL
                      + f'<a href="{validate_site.CHEN_SOURCE}">來源</a>')
        self.write_html(self.html.replace('內科</article>', f'內科{credential}</article>', 1))
        self.validate()

    def test_chen_review_credential_requires_source_in_same_card(self):
        html = self.html.replace('內科</article>',
                                 f'內科{validate_site.CHEN_REVIEW_CREDENTIAL}</article>', 1)
        self.write_html(html + f'<a href="{validate_site.CHEN_SOURCE}">來源</a>')
        with self.assertRaisesRegex(ValueError, 'requires its source link'):
            self.validate()

    def test_review_credential_cannot_be_reused_as_other_claims(self):
        credential = (validate_site.CHEN_REVIEW_CREDENTIAL
                      + f'<a href="{validate_site.CHEN_SOURCE}">來源</a>')
        html = self.html.replace('內科</article>', f'內科{credential}</article>', 1)
        for other_claim in (validate_site.CHEN_REVIEW_CREDENTIAL,
                            '<p>良醫健康網第一名</p>', '<p>最佳診所</p>'):
            with self.subTest(claim=other_claim):
                self.write_html(html + other_claim)
                with self.assertRaisesRegex(ValueError, 'Banned text found'):
                    self.validate()

    def test_review_credential_in_another_doctor_card_is_rejected(self):
        credential = (validate_site.CHEN_REVIEW_CREDENTIAL
                      + f'<a href="{validate_site.CHEN_SOURCE}">來源</a>')
        self.write_html(self.html.replace('內科／胸腔內科</article>',
                                         f'內科／胸腔內科{credential}</article>'))
        with self.assertRaisesRegex(ValueError, 'Banned text found'):
            self.validate()

    def test_removed_booking_phrases_are_rejected(self):
        for phrase in ('限複診', '目前無線上預約功能'):
            with self.subTest(phrase=phrase):
                self.write_html(self.html + f'<p>{phrase}</p>')
                with self.assertRaisesRegex(ValueError, 'Banned text found'):
                    self.validate()

    def test_in_page_links_resolve_to_ids(self):
        self.write_html(self.html + '<a href="#missing">x</a>')
        with self.assertRaisesRegex(ValueError, 'Broken section link'):
            self.validate()

    def test_personal_site_canonical_is_rejected(self):
        self.write_html(self.html + '<link rel="canonical" href="https://kenkao0127-droid.github.io/dr-kao-personal-website/">')
        with self.assertRaisesRegex(ValueError, 'canonical'):
            self.validate()

    def test_other_personal_site_links_are_rejected(self):
        self.write_html(self.html + '<a href="https://kenkao0127-droid.github.io/other/">x</a>')
        with self.assertRaisesRegex(ValueError, 'personal site'):
            self.validate()

    def test_missing_required_link_is_rejected(self):
        self.write_html(self.html.replace('https://www.cm166.com.tw/', 'https://example.com/'))
        with self.assertRaisesRegex(ValueError, 'Missing required clinic links'):
            self.validate()

    def test_general_medicine_list_must_match_in_both_places(self):
        self.write_html(self.html.replace('<small>' + validate_site.GENERAL_MEDICINE + '</small>', '<small>感冒、發燒</small>'))
        with self.assertRaisesRegex(ValueError, 'General medicine list'):
            self.validate()

    def test_photo_order_must_be_chen_chang_kao(self):
        html = self.html.replace('doctor-chen.webp', 'TMP').replace('doctor-chang.webp', 'doctor-chen.webp').replace('TMP', 'doctor-chang.webp')
        self.write_html(html)
        with self.assertRaisesRegex(ValueError, 'Images must be exactly'):
            self.validate()

    def test_photo_alt_must_name_the_doctor(self):
        self.write_html(self.html.replace('alt="張峻愷醫師"', 'alt="醫師"'))
        with self.assertRaisesRegex(ValueError, 'alt text must be'):
            self.validate()

    def test_photo_must_be_webp_without_metadata_and_small(self):
        photo = self.root / 'assets/images/doctor-kao.webp'
        for payload, message in ((b'GIF89a' + b'\0' * 20, 'must be WebP'),
                                 (b'RIFF\x04\0\0\0WEBPEXIF', 'no metadata'),
                                 (b'RIFF\x04\0\0\0WEBP' + b'\0' * 150_001, 'too large')):
            with self.subTest(message=message):
                photo.write_bytes(payload)
                with self.assertRaisesRegex(ValueError, message):
                    self.validate()

    def test_photo_dimensions_must_match(self):
        self.write_html(self.html.replace('width="900" height="675" alt="高傳紘醫師"', 'width="300" height="300" alt="高傳紘醫師"'))
        with self.assertRaisesRegex(ValueError, 'same width/height'):
            self.validate()

    def test_clinic_link_not_allowed_in_about_section(self):
        self.write_html(self.html.replace('<section id="about">about</section>', '<section id="about"><a href="https://www.cm166.com.tw/">x</a></section>'))
        with self.assertRaisesRegex(ValueError, 'about section'):
            self.validate()

    def test_clinic_link_count_is_exact(self):
        self.write_html(self.html + '<a href="https://www.cm166.com.tw/">extra</a>')
        with self.assertRaisesRegex(ValueError, 'exactly three'):
            self.validate()

    def test_three_doctor_cards_required(self):
        self.write_html(self.html.replace('<article class="doctor-card"><figure><img src="assets/images/doctor-chang.webp"', '<div><figure><img src="assets/images/doctor-chang.webp"'))
        with self.assertRaisesRegex(ValueError, 'exactly three doctor cards'):
            self.validate()

    def test_endoscopy_must_be_marked_in_preparation(self):
        self.write_html(self.html.replace('<span class="badge">籌備中</span>', ''))
        with self.assertRaisesRegex(ValueError, 'in preparation'):
            self.validate()


if __name__ == '__main__':
    unittest.main()
