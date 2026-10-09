# メーカーのカタログ・製品画像・ロゴを取得して assets/ に保存するスクリプト
# 取得に失敗したものは前回保存分を残す（リンク切れ対策）
import datetime, hashlib, io, json, os, time, urllib.request
from PIL import Image, ImageChops, ImageDraw

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
    if url.startswith('file://'):
        return open(url[7:], 'rb').read(), ''
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ja,en;q=0.8'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read(), r.headers.get('Content-Type', '')


def save_image(url, base, maxw=900, crop=None, erase=None, trim=False):
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
    w, h = im.size
    # erase: 画像内の文字やアイコンを白で塗りつぶす範囲（幅・高さに対する割合）
    for x0, y0, x1, y1 in (erase or []):
        ImageDraw.Draw(im).rectangle([x0 * w, y0 * h, x1 * w, y1 * h], fill='white')
    # crop: 製品部分だけを切り出す範囲（幅・高さに対する割合）
    if crop:
        x0, y0, x1, y1 = crop
        im = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    # trim: 切り出した後、周りの余白（透明・白）を詰める
    if trim:
        if im.mode == 'RGBA' and im.getchannel('A').getextrema()[0] < 250:
            box = im.getchannel('A').point(lambda v: 255 if v > 16 else 0).getbbox()
        else:
            white = Image.new('RGB', im.size, (255, 255, 255))
            box = ImageChops.difference(im.convert('RGB'), white).convert('L').point(
                lambda v: 255 if v > 24 else 0).getbbox()
        if box:
            pad = int(max(im.size) * 0.03)
            im = im.crop((max(0, box[0] - pad), max(0, box[1] - pad),
                          min(im.width, box[2] + pad), min(im.height, box[3] + pad)))
    im.thumbnail((maxw, maxw))
    path = base + '.webp'
    im.save(path, 'WEBP', quality=86)
    return path


def save_catalog_pages(base, count, path):
    # ページごとに分かれたWebカタログ（1.pdf, 2.pdf ...）を1つのPDFにまとめて保存
    import pymupdf
    out = pymupdf.open()
    for n in range(1, count + 1):
        data, ct = get(base.replace('{n}', str(n)))
        if not data.startswith(b'%PDF'):
            raise ValueError(f'{n}ページ目がPDFではありません')
        out.insert_pdf(pymupdf.open(stream=data, filetype='pdf'))
    out.save(path, garbage=3, deflate=True)
    return path


def image_from_catalog(pdf_path, page, xref, base, maxw=900, trim=True):
    # カタログPDFの中の製品写真（画像）を取り出して保存
    import pymupdf
    doc = pymupdf.open(pdf_path)
    pix = pymupdf.Pixmap(doc, xref)
    if pix.n - pix.alpha > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    smask = [im for im in doc[page - 1].get_images(full=True) if im[0] == xref]
    if smask and smask[0][1]:
        mask = pymupdf.Pixmap(doc, smask[0][1])
        pix = pymupdf.Pixmap(pix, mask)
    tmp = base + '.tmp.png'
    pix.save(tmp)
    try:
        return save_image('file://' + os.path.abspath(tmp), base, maxw=maxw, trim=trim)
    finally:
        os.remove(tmp)


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
            entry['image'] = save_image(s['image'], 'assets/images/' + key,
                                        crop=s.get('image_crop'), erase=s.get('image_erase'),
                                        trim=s.get('image_trim', False))
        except Exception as e:
            errors.append(f'image: {e}')
    if s.get('catalog_pages'):
        cp = s['catalog_pages']
        try:
            entry['catalog_local'] = save_catalog_pages(cp['base'], cp['count'], f'assets/catalogs/{key}.pdf')
        except Exception as e:
            errors.append(f'catalog_pages: {e}')
    elif s.get('catalog'):
        try:
            entry['catalog_local'] = save_pdf(s['catalog'], f'assets/catalogs/{key}.pdf')
        except Exception as e:
            errors.append(f'catalog: {e}')
    if s.get('image_from_catalog'):
        ic = s['image_from_catalog']
        src_pdf = 'assets/catalogs/' + ic['catalog_key'] + '.pdf'
        try:
            entry['image'] = image_from_catalog(src_pdf, ic['page'], ic['xref'], 'assets/images/' + key)
        except Exception as e:
            errors.append(f'image_from_catalog: {e}')
    entry['checked'] = today
    entry['errors'] = errors
    man['series'][key] = entry
    print('series', key, 'errors:', errors or 'なし')

def save_manifest():
    json.dump(man, open(MAN, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


# まず取得できたファイルを保存（このあとのWeb魚拓が遅くても取得分は残る）
save_manifest()

# Web魚拓（Internet Archive）にも保存して、メーカー側のリンク切れに備える
# 時間がかかるため、1回の実行で試すのは最大8件。直近25日以内に保存済みのものは飛ばす
def recent(d):
    try:
        return (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(d)).days < 25
    except Exception:
        return False

budget = 8
for s in src.get('series', []):
    entry = man['series'][s['key']]
    for field, url in (('catalog', s.get('catalog')), ('page', s.get('page'))):
        if not url or recent(entry.get(field + '_archived_on', '')) or budget <= 0:
            continue
        budget -= 1
        if archive(url):
            entry[field + '_archive'] = 'https://web.archive.org/web/' + url
            entry[field + '_archived_on'] = today
    save_manifest()
print('完了')
