from flask import jsonify, request
from pydantic import ValidationError

from app.api import api_bp
from app.auth.decorators import admin_required, aprovado_required
from app.extensions import db, limiter
from app.models import ConfiguracaoSite, ConfiguracaoCards, TipoFundo
from app.schemas import ConfiguracaoSiteIn, ConfiguracaoCardsIn


@api_bp.get("/configuracao")
def obter_configuracao():
    """Rota pública e sem autenticação: é o que alimenta a landing page,
    vista por qualquer visitante antes de entrar no sistema. Não expõe
    nenhum dado sensível — só nome da empresa, textos e mídia de fundo."""
    config = ConfiguracaoSite.obter()
    return jsonify(config.to_dict())


@api_bp.put("/configuracao")
@admin_required
@limiter.limit("30 per minute")
def atualizar_configuracao():
    config = ConfiguracaoSite.obter()
    payload = request.get_json(silent=True) or {}
    try:
        data = ConfiguracaoSiteIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    config.nome_empresa = data.nomeEmpresa
    config.slogan = data.slogan
    config.descricao = data.descricao
    config.tipo_fundo = TipoFundo(data.tipoFundo)
    config.imagem_fundo_url = data.imagemFundoUrl or None
    config.video_fundo_url = data.videoFundoUrl or None
    config.logo_url = data.logoUrl or None
    config.cor_destaque = data.corDestaque

    db.session.commit()
    return jsonify(config.to_dict())


@api_bp.get("/configuracao/cards")
@aprovado_required
def obter_configuracao_cards():
    """Qualquer usuário aprovado precisa ler isso (é o que dá os rótulos e
    o estilo aplicados nos cards que ele mesmo vê) — só a EDIÇÃO é
    restrita ao admin."""
    return jsonify(ConfiguracaoCards.obter().to_dict())


@api_bp.put("/configuracao/cards")
@admin_required
@limiter.limit("30 per minute")
def atualizar_configuracao_cards():
    """Personalização dos cards: só afeta rótulos/aparência — nunca os
    dados cadastrados das cidades. Aplicado automaticamente em todos os
    cards (não precisa editar cidade por cidade)."""
    config = ConfiguracaoCards.obter()
    payload = request.get_json(silent=True) or {}
    try:
        data = ConfiguracaoCardsIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    # Mescla com o que já existe (permite atualizar só uma chave de cada
    # vez do front, sem precisar reenviar o dicionário inteiro).
    config.rotulos = {**(config.rotulos or {}), **data.rotulos}
    config.estilo = {**(config.estilo or {}), **data.estilo}
    db.session.commit()
    return jsonify(config.to_dict())
