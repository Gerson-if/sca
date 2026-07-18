"""Sincronização quase em tempo real via *polling* leve.

Por que polling e não WebSocket: a stack atual (Gunicorn sync workers +
Flask-Session baseado em arquivo/Redis) não tem um servidor assíncrono
rodando; adicionar WebSocket de verdade (Flask-SocketIO) trocaria a classe
do worker do Gunicorn (eventlet/gevent) e mudaria como a sessão precisa ser
compartilhada entre processos — uma mudança de infraestrutura maior do que
cabe aqui com segurança.

Em vez disso, o front-end consulta `GET /api/sync` a cada poucos segundos
(ver `verificarSincronizacao()` em app.js) e compara os marcadores abaixo
com os que já tinha da última vez. Qualquer diferença dispara um recarregamento
só daquela seção (avisos, chat, cidades) e, quando aplicável, uma notificação
do navegador — o efeito para quem está usando o sistema é "tempo real" com
poucos segundos de atraso, sem a complexidade operacional de WebSockets.
"""

from flask import jsonify
from sqlalchemy import func

from app.api import api_bp
from app.auth.decorators import aprovado_required
from app.extensions import db
from app.models import Aviso, Cidade, ChatMessage, User


@api_bp.get("/sync")
@aprovado_required
def sincronizar():
    ultimo_aviso, total_avisos = db.session.query(
        func.max(Aviso.updated_at), func.count(Aviso.id)
    ).first()
    ultima_cidade, total_cidades = db.session.query(
        func.max(Cidade.updated_at), func.count(Cidade.id)
    ).first()
    ultima_mensagem = db.session.query(func.max(ChatMessage.id)).scalar()
    ultimo_usuario, total_usuarios = db.session.query(
        func.max(User.created_at), func.count(User.id)
    ).first()

    # Combina "última alteração" + "quantidade de linhas": um UPDATE muda o
    # primeiro, mas um DELETE só muda o segundo (a data da linha mais
    # recentemente alterada pode continuar igual mesmo depois de apagar
    # outra linha mais antiga) — sem a contagem, exclusões não seriam
    # detectadas por quem já tinha a lista aberta em outra aba/dispositivo.
    return jsonify({
        "avisos": f"{total_avisos}:{ultimo_aviso.isoformat() if ultimo_aviso else ''}",
        "cidades": f"{total_cidades}:{ultima_cidade.isoformat() if ultima_cidade else ''}",
        "chatUltimoId": ultima_mensagem or 0,
        "usuarios": f"{total_usuarios}:{ultimo_usuario.isoformat() if ultimo_usuario else ''}",
    })
