import os
import uuid

from flask import current_app, jsonify, request
from PIL import Image, UnidentifiedImageError

from app.api import api_bp
from app.auth.decorators import admin_required
from app.extensions import limiter


def _extensao_permitida(filename: str, extensoes: set) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in extensoes


def _extensao_video(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _assinatura_video_valida(cabecalho: bytes) -> bool:
    """Confere a "assinatura" binária do arquivo (magic bytes), não apenas a
    extensão — evita que um arquivo qualquer renomeado para .mp4/.webm seja
    aceito como vídeo."""
    if len(cabecalho) < 12:
        return False
    if cabecalho[4:8] == b"ftyp":  # família MP4/MOV (ISO Base Media)
        return True
    if cabecalho[:4] == b"\x1a\x45\xdf\xa3":  # WebM/Matroska (EBML)
        return True
    return False


def processar_e_salvar_imagem(arquivo, max_dim: int | None = None) -> str:
    """Valida (assinatura real via Pillow, não só extensão), redimensiona e
    salva uma imagem enviada por upload. Devolve a URL pública (/static/uploads/...).
    Lança ValueError com uma mensagem amigável se o arquivo for inválido.

    Compartilhado entre o upload de mídia do admin (cidades/landing page) e
    o upload de foto de perfil do próprio usuário — mesma validação de
    segurança nos dois casos.
    """
    if arquivo.filename == "":
        raise ValueError("Nenhum arquivo selecionado.")

    if not _extensao_permitida(arquivo.filename, current_app.config["ALLOWED_IMAGE_EXTENSIONS"]):
        permitidas = ", ".join(sorted(current_app.config["ALLOWED_IMAGE_EXTENSIONS"]))
        raise ValueError(f"Formato não suportado. Use: {permitidas}.")

    try:
        imagem = Image.open(arquivo.stream)
        imagem.verify()  # valida que é realmente uma imagem
        arquivo.stream.seek(0)
        imagem = Image.open(arquivo.stream).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise ValueError("Arquivo de imagem inválido ou corrompido.")

    imagem.thumbnail((max_dim or current_app.config["IMAGE_MAX_DIMENSION"],) * 2)

    nome_final = f"{uuid.uuid4().hex}.jpg"
    caminho_destino = os.path.join(current_app.config["UPLOAD_FOLDER"], nome_final)
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    imagem.save(caminho_destino, format="JPEG", quality=85, optimize=True)

    return f"/static/uploads/{nome_final}"


@api_bp.post("/uploads/imagem")
@admin_required
@limiter.limit("20 per minute")
def upload_imagem():
    """Recebe uma imagem (ex.: ícone/foto associada a uma cidade, ou fundo
    da landing page), valida, redimensiona com Pillow e salva em
    app/static/uploads."""
    if "arquivo" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado (campo 'arquivo')."}), 400

    try:
        url_publica = processar_e_salvar_imagem(request.files["arquivo"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"url": url_publica}), 201


@api_bp.post("/uploads/video")
@admin_required
@limiter.limit("10 per minute")
def upload_video():
    """Recebe um vídeo curto (usado como fundo animado da landing page).
    Não é reprocessado (Pillow só trata imagem), mas passa por validação de
    extensão, assinatura binária (magic bytes) e tamanho máximo antes de
    ser salvo."""
    if "arquivo" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado (campo 'arquivo')."}), 400

    arquivo = request.files["arquivo"]
    if arquivo.filename == "":
        return jsonify({"error": "Nenhum arquivo selecionado."}), 400

    extensoes = current_app.config["ALLOWED_VIDEO_EXTENSIONS"]
    if not _extensao_permitida(arquivo.filename, extensoes):
        permitidas = ", ".join(sorted(extensoes))
        return jsonify({"error": f"Formato não suportado. Use: {permitidas}."}), 400

    cabecalho = arquivo.stream.read(16)
    arquivo.stream.seek(0)
    if not _assinatura_video_valida(cabecalho):
        return jsonify({"error": "Arquivo de vídeo inválido ou corrompido."}), 400

    # Confere o tamanho real (Content-Length pode ser omitido/forjado).
    arquivo.stream.seek(0, os.SEEK_END)
    tamanho = arquivo.stream.tell()
    arquivo.stream.seek(0)
    limite = current_app.config["MAX_VIDEO_SIZE"]
    if tamanho > limite:
        return jsonify({"error": f"Vídeo muito grande (máx. {limite // (1024 * 1024)} MB)."}), 413

    ext = _extensao_video(arquivo.filename)
    nome_final = f"{uuid.uuid4().hex}.{ext}"
    caminho_destino = os.path.join(current_app.config["UPLOAD_FOLDER"], nome_final)
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    arquivo.save(caminho_destino)

    url_publica = f"/static/uploads/{nome_final}"
    return jsonify({"url": url_publica}), 201
