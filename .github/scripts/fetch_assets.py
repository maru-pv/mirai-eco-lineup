# メーカーのカタログ・製品画像・ロゴを取得して assets/ に保存するスクリプト
# 取得に失敗したものは前回保存分を残す（リンク切れ対策）
import datetime, hashlib, io, json, os, time, urllib.request
from PIL import Image

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0 Safari/537.36')
SRC = 'assets/sources.json'
MAN = 'assets/manifest.json'
for d in ('assets/logos', 'assets/images', 'assets/catalogs'):
    os.makedirs(d, exist_ok=True)

src = json.load(open(SRC, encoding='utf-8'))
man = json.load(open(MAN, encoding='utf-8')) if os.path.exists(MAN) else {}
man.setdefault('logos', {})
man.setdefault('series', {})
today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')


def get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ja,en;q=0.8'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read(), r.headers.get('Content-Type', '')


def save_image(url, base, maxw=900):
    data, ct = get(url)
    if url.lower().split('?')[0].endswith('.svg') or 'svg' in ct:
        if b'<svg' not in data[:4000].lower():
            raise ValueError('SVGではありません')
        path = base + '.svg'
        open(path, 'wb').write(data)
        return path
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode not in ('RGB', 'RGBA'):
        im = im.convert('RGBA')
    im.thumbnail((maxw, maxw))
    path = base + '.webp'
    im.save(path, 'WEBP', quality=86)
    return path


def save_pdf(url, path):
    data, ct = get(url)
    if not data.startswith(b'%PDF'):
        raise ValueError('PDFではありません (' + ct + ')')
    open(path, 'wb').write(data)
    return path


def archive(url):
    try:
        req = urllib.request.Request('https://web.archive.org/save/' + url,
                                     headers={'User-Agent': UA})
        urllib.request.urlopen(req, timeout=45).read(100)
        time.sleep(3)
        return True
    except Exception as e:
        print('  [archive失敗]', url, e)
        time.sleep(3)
        return False


for maker, url in src.get('logos', {}).items():
    entry = man['logos'].get(maker, {})
    slug = 'logo-' + hashlib.md5(maker.encode('utf-8')).hexdigest()[:8]
    try:
        entry['file'] = save_image(url, 'assets/logos/' + slug, maxw=600)
        entry['checked'] = today
        entry.pop('error', None)
        print('logo OK', maker)
    except Exception as e:
        entry['error'] = f'{today}: {e}'
        print('logo NG', maker, e)
    entry['source'] = url
    man['logos'][maker] = entry

for s in src.get('series', []):
    key = s['key']
    entry = man['series'].get(key, {})
    entry.update({'page': s.get('page'), 'catalog_official': s.get('catalog')})
    errors = []
    if s.get('image'):
        try:
            entry['image'] = save_image(s['image'], 'assets/images/' + key)
        except Exception as e:
            errors.append(f'image: {e}')
    if s.get('catalog'):
        try:
            entry['catalog_local'] = save_pdf(s['catalog'], f'assets/catalogs/{key}.pdf')
        except Exception as e:
            errors.append(f'catalog: {e}')
    entry['checked'] = today
    entry['errors'] = errors
    man['series'][key] = entry
    print('series', key, 'errors:', errors or 'なし')

def save_manifest():
    json.dump(man, open(MAN, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


# まず取得できたファイルを保存（このあとのWeb魚拓が遅くても取得分は残る）
save_manifest()

# Web魚拓（Internet Archive）にも保存して、メーカー側のリンク切れに備える
for s in src.get('series', []):
    entry = man['series'][s['key']]
    if s.get('catalog') and archive(s['catalog']):
        entry['catalog_archive'] = 'https://web.archive.org/web/' + s['catalog']
    if s.get('page') and archive(s['page']):
        entry['page_archive'] = 'https://web.archive.org/web/' + s['page']
    save_manifest()
print('完了')
