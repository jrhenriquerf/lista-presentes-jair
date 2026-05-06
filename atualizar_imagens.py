"""
=============================================================
  atualizar_imagens.py  (v2 — corrigido lazy loading ML)
  Extrai imagens dos links do Mercado Livre e embute no HTML
=============================================================

DEPENDÊNCIAS — rode uma vez antes:
    pip install requests beautifulsoup4 Pillow

USO:
    python atualizar_imagens.py
=============================================================
"""

import re
import json
import base64
import time
import sys
from io import BytesIO
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
    from PIL import Image
except ImportError:
    print("❌ Dependências faltando. Rode:")
    print("   pip install requests beautifulsoup4 Pillow")
    sys.exit(1)

# ─────────────────────────────────────────────
#  CONFIGURAÇÃO: nome do card → URL do produto
# ─────────────────────────────────────────────
PRODUTOS = {
    "Kit Natação":        "https://www.mercadolivre.com.br/oculos-nataco-espelhado-hammerhead-olympic-mirror-fogfend-cor-dourado/p/MLB50808893",
    "Luva de Boxe":       "https://produto.mercadolivre.com.br/MLB-2932908455-luva-de-boxe-muay-thai-adidas-hybrid-80-black-black-_JM",
    "Super Band":         "https://www.mercadolivre.com.br/kit-super-band-4-intensidades-odin-fit-elasticos-power-band-treino/p/MLB28706883",
    "Camiseta Insider":   "https://produto.mercadolivre.com.br/MLB-2222397098-daily-t-shirt-insider-_JM",
    "Teclado Mecânico":   "https://www.mercadolivre.com.br/teclado-mecnico-aula-f99-gamer-preto-e-cinza-com-contorno-rgb-sem-fio-wireless-tri-mode-bluetooth-50-24g-usb-hotswap-layout-96-compativel-pc-notebook-mac-ideal-para-jogos-e-trabalh/p/MLB64973154",
    "Mouse Gamer":        "https://www.mercadolivre.com.br/mouse-gamer-sem-fio-logitech-g-pro-x-superlight-2-para-jogos/p/MLB28295187",
    "Suporte Articulado": "https://www.mercadolivre.com.br/suporte-de-braco-para-monitor-duplo-north-bayou-f160-17-a-27-cor-cinza-escuro/p/MLB39258231",
    "Câmera Veicular":    "https://www.mercadolivre.com.br/cmera-de-painel-de-3-canais-ddpai-z90-master-4k-para-carros/p/MLB2083649264",
    "Echo Show 8":        "https://www.mercadolivre.com.br/echo-show-8-smart-display-3-geracao-preta-amazon/up/MLBU3899897181",
    "Aspirador Robô":     "https://www.mercadolivre.com.br/dreame-d10-plus-gen-2-rob-aspirador-e-mopa-com-base-127v-branco/p/MLB48904538",
    "TV Sala":            "https://www.mercadolivre.com.br/smart-tv-tcl-55-polegadas-qled-mini-led-4k-c6k-wifi-bluetooth-google-tv-4-hdmi-144hz-hdr10-55c6k/p/MLB48808732",
    "Controle para PC":   "https://www.mercadolivre.com.br/controle-gamesir-cyclone-2-bundle-edition-dock-carregamento-para-pc-switch-ios-android-steam-celular-hall-effect-branco/p/MLB45861096",
}

HTML_INPUT  = Path("lista-presentes.html")
HTML_OUTPUT = Path("lista-presentes-imagens.html")

IMG_WIDTH  = 600
IMG_HEIGHT = 400

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

IMG_HEADERS = {
    **HEADERS,
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://www.mercadolivre.com.br/",
}


def log(msg, emoji=""):
    print(f"{emoji}  {msg}" if emoji else f"    {msg}")


def extrair_item_id(url: str) -> str | None:
    """Extrai o ID do item MLB da URL."""
    # Formato /MLB-1234567 ou MLB1234567 ou item_id=MLB1234567
    m = re.search(r'MLB[\-]?(\d{6,12})', url, re.IGNORECASE)
    return f"MLB{m.group(1)}" if m else None


def buscar_via_api_ml(item_id: str) -> str | None:
    """
    Usa a API pública do ML para pegar a URL da imagem.
    Muito mais confiável que scraping HTML.
    """
    # Tenta API de produto direto
    api_url = f"https://api.mercadolibre.com/items/{item_id}"
    try:
        resp = requests.get(api_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            # Pega a primeira imagem de alta qualidade
            pictures = data.get("pictures", [])
            if pictures:
                # Prefere URL segura e de maior tamanho
                pic = pictures[0]
                url = pic.get("secure_url") or pic.get("url", "")
                # Forçar tamanho máximo substituindo sufixo
                url = re.sub(r'-[A-Z]\d+x\d+\.', '-O.', url)
                return url
            # Thumbnail como fallback
            thumb = data.get("thumbnail", "")
            if thumb:
                return re.sub(r'-[A-Z]\d+x\d+\.', '-O.', thumb)
    except Exception as e:
        log(f"API direta falhou ({e}), tentando busca...")

    return None


def buscar_via_api_search(url_produto: str) -> str | None:
    """
    Para URLs de tipo /p/MLB... (produto agrupado),
    busca pelo ID do produto na API de search.
    """
    # Extrai o ID do produto agrupado (MLB + números no final da URL)
    m = re.search(r'/p/(MLB\d+)', url_produto, re.IGNORECASE)
    if not m:
        return None

    product_id = m.group(1)
    search_url = f"https://api.mercadolibre.com/products/{product_id}"
    try:
        resp = requests.get(search_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            pictures = data.get("pictures", [])
            if pictures:
                url = pictures[0].get("secure_url") or pictures[0].get("url", "")
                url = re.sub(r'-[A-Z]\d+x\d+\.', '-O.', url)
                return url
    except Exception as e:
        log(f"API produto agrupado falhou: {e}")

    return None


def buscar_via_scraping(produto_url: str) -> str | None:
    """
    Fallback: scraping HTML buscando data-src e JSON embutido.
    """
    try:
        resp = requests.get(produto_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        log(f"Erro ao acessar página: {e}", "⚠️")
        return None

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Estratégia 1: JSON-LD com imagem
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            # Pode ser lista ou dict
            items = data if isinstance(data, list) else [data]
            for item in items:
                img = item.get("image")
                if isinstance(img, str) and img.startswith("http"):
                    return img
                if isinstance(img, list) and img:
                    return img[0]
        except Exception:
            continue

    # Estratégia 2: JSON __PRELOADED_STATE__ embutido na página
    m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.+?\});\s*</script>', html, re.DOTALL)
    if m:
        try:
            state = json.loads(m.group(1))
            # Navegar pela estrutura para achar imagens
            def find_images(obj, depth=0):
                if depth > 10:
                    return []
                results = []
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in ("secure_url", "url") and isinstance(v, str) and "mlstatic" in v:
                            results.append(v)
                        else:
                            results.extend(find_images(v, depth+1))
                elif isinstance(obj, list):
                    for item in obj[:5]:
                        results.extend(find_images(item, depth+1))
                return results

            imgs = find_images(state)
            if imgs:
                url = re.sub(r'-[A-Z]\d+x\d+\.', '-O.', imgs[0])
                return url
        except Exception:
            pass

    # Estratégia 3: data-src nas tags img (lazy loading)
    for img in soup.find_all("img"):
        for attr in ("data-src", "data-lazy", "data-original", "data-zoom-image"):
            src = img.get(attr, "")
            if src and src.startswith("http") and "mlstatic" in src:
                return src

    # Estratégia 4: qualquer URL mlstatic no HTML
    urls = re.findall(r'https://[^"\']+mlstatic\.com/[^"\']+\.(?:jpg|jpeg|png|webp)', html)
    if urls:
        # Preferir URLs sem sufixo de tamanho pequeno
        for u in urls:
            if "-O." in u or "D_NQ_NP" in u:
                return re.sub(r'-[A-Z]\d+x\d+\.', '-O.', u)
        return re.sub(r'-[A-Z]\d+x\d+\.', '-O.', urls[0])

    return None


def get_image_url(nome: str, produto_url: str) -> str | None:
    """Orquestra todas as estratégias para achar a imagem."""

    # Estratégia A: API do produto agrupado (URLs com /p/MLB...)
    if "/p/MLB" in produto_url or "/up/MLB" in produto_url:
        url = buscar_via_api_search(produto_url)
        if url:
            log("Imagem via API produto agrupado ✓")
            return url

    # Estratégia B: API direta pelo ID do item
    item_id = extrair_item_id(produto_url)
    if item_id:
        url = buscar_via_api_ml(item_id)
        if url:
            log("Imagem via API ML ✓")
            return url

    # Estratégia C: scraping da página HTML
    log("Tentando scraping da página...")
    url = buscar_via_scraping(produto_url)
    if url:
        log("Imagem via scraping ✓")
        return url

    return None


def download_e_encode(image_url: str) -> str | None:
    """Baixa imagem, redimensiona e retorna base64 data URI."""
    if not image_url or image_url.startswith("data:"):
        return None

    try:
        resp = requests.get(image_url, headers=IMG_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        log(f"Erro ao baixar imagem: {e}", "⚠️")
        return None

    try:
        img = Image.open(BytesIO(resp.content)).convert("RGB")

        # Redimensionar com crop central
        ratio = max(IMG_WIDTH / img.width, IMG_HEIGHT / img.height)
        new_w, new_h = int(img.width * ratio), int(img.height * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - IMG_WIDTH) // 2
        top  = (new_h - IMG_HEIGHT) // 2
        img  = img.crop((left, top, left + IMG_WIDTH, top + IMG_HEIGHT))

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        log(f"Erro ao processar imagem: {e}", "⚠️")
        return None


def substituir_no_html(html: str, alt_text: str, nova_src: str) -> str:
    """Substitui o src da img com o alt correspondente."""
    nova = f'src="{nova_src}"'

    # Padrão: alt vem depois do src
    p1 = re.compile(
        r'(<img\s[^>]*alt="' + re.escape(alt_text) + r'"[^>]*?)\s*src="[^"]*"',
        re.DOTALL
    )
    # Padrão: src vem antes do alt
    p2 = re.compile(
        r'(<img\s[^>]*?)\s*src="[^"]*"([^>]*?alt="' + re.escape(alt_text) + r'")',
        re.DOTALL
    )

    result, n = p1.subn(lambda m: m.group(1) + ' ' + nova, html)
    if n == 0:
        result, n = p2.subn(lambda m: f'{m.group(1)} {nova}{m.group(2)}', html)
    if n == 0:
        log(f'⚠️  alt="{alt_text}" não encontrado no HTML')
    return result


def main():
    if not HTML_INPUT.exists():
        log(f"Arquivo '{HTML_INPUT}' não encontrado!", "❌")
        log("Coloque este script na mesma pasta que lista-presentes.html")
        sys.exit(1)

    html = HTML_INPUT.read_text(encoding="utf-8")
    total = len(PRODUTOS)

    print("=" * 55)
    print(f"  Processando {total} produtos...")
    print("=" * 55)

    sucesso = 0
    for i, (nome, url) in enumerate(PRODUTOS.items(), 1):
        log(f"[{i}/{total}] {nome}", "🔍")

        img_url = get_image_url(nome, url)
        if not img_url:
            log("Nenhuma imagem encontrada, mantendo SVG", "⏭️")
            time.sleep(1)
            continue

        log("Baixando e codificando...", "📥")
        data_uri = download_e_encode(img_url)
        if not data_uri:
            log("Falha ao baixar, mantendo SVG", "⏭️")
            time.sleep(1)
            continue

        html = substituir_no_html(html, nome, data_uri)
        kb = len(data_uri) * 3 // 4 // 1024
        log(f"✅ Substituído! ({kb} KB)")
        sucesso += 1
        time.sleep(1.5)

    HTML_OUTPUT.write_text(html, encoding="utf-8")
    tamanho_kb = HTML_OUTPUT.stat().st_size // 1024

    print("=" * 55)
    print(f"  ✅ Concluído! {sucesso}/{total} imagens substituídas")
    print(f"  📄 Arquivo: {HTML_OUTPUT}  ({tamanho_kb} KB)")
    print("=" * 55)


if __name__ == "__main__":
    main()
