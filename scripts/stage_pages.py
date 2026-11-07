"""Stage active and last-live catalog snapshots for GitHub Pages."""
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


BASE = 'https://libremaker700.github.io/apple-tv-cn-catalog/'
DOCS = Path(__file__).resolve().parent.parent / 'docs'


def previous_manifest(prefix):
    try:
        with urlopen(BASE + prefix + 'version.json', timeout=20) as response:
            return json.loads(response.read(2 * 1024 * 1024))
    except HTTPError as error:
        if error.code != 404:
            raise
        return None


def snapshot_files(manifest, name):
    release = manifest['catalog_path' if name == 'catalog' else 'path']
    if not re.fullmatch(r'releases/[a-f0-9]{64}/' + name + r'\.json', release):
        raise ValueError('Unexpected release path in Pages manifest')
    images = set(manifest['images']) | set(manifest.get('titleLogos', {}))
    if any(not re.fullmatch(r'images/[a-f0-9]{64}\.(?:jpg|png)', ref) for ref in images):
        raise ValueError('Unexpected image path in Pages manifest')
    return images | {release}


def stage(output):
    output.mkdir(parents=True, exist_ok=False)
    files = {path.relative_to(DOCS) for path in DOCS.rglob('*') if path.is_file()
             and path.relative_to(DOCS).parts[0] not in ('home', 'images', 'releases')}
    files.update(path.relative_to(DOCS) for path in (DOCS / 'home').iterdir() if path.is_file())
    for prefix, name in (('', 'catalog'), ('home/', 'home')):
        current = json.loads((DOCS / prefix / 'version.json').read_text(encoding='utf-8'))
        for manifest in (current, previous_manifest(prefix)):
            if manifest:
                files.update(Path(prefix) / path for path in snapshot_files(manifest, name))
    for relative in sorted(files):
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DOCS / relative, target)
    size = sum((output / path).stat().st_size for path in files)
    print(f'Pages: {len(files)} files, {size / 1024 ** 2:.1f} MiB')


if __name__ == '__main__':
    stage(Path(sys.argv[1]))
