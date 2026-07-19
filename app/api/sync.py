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
from flask_login import current_user
from sqlalchemy import func

from app.api import api_bp
from app.auth.decorators import aprovado_required
from app.extensions import db, limiter
from app.models import Aviso, Cidade, ChatMessage, User


@api_bp.get("/sync")
@aprovado_required
# O front-end consulta esta rota a cada 6s por usuário logado (ver
# verificarSincronizacao() em app.js) — isso já são ~600 req/hora só de UM
# usuário. Sem um limite próprio, a rota caía no default_limits global de
# 200/hora (pensado para proteger endpoints sensíveis, não polling), e como
# o limitador conta por IP, bastavam poucos minutos com duas pessoas na
# mesma rede para estourar a cota: a partir daí toda checagem de
# sincronização voltava 429, era engolida pelo catch silencioso do
# front-end, e o "tempo real" (notificação de chat, avisos etc.) parava de
# funcionar sem nenhum erro visível. 40/min dá folga confortável para vários
# usuários simultâneos atrás do mesmo IP sem abrir espaço de abuso.
@limiter.limit("40 per minute")
def sincronizar():
    ultimo_aviso, total_avisos = db.session.query(
        func.max(Aviso.updated_at), func.count(Aviso.id)
    ).first()
    ultima_cidade, total_cidades = db.session.query(
        func.max(Cidade.updated_at), func.count(Cidade.id)
    ).first()
    # IMPORTANTE: exclui as próprias mensagens do usuário logado. Antes, o
    # marcador era o maior id de ChatMessage no sistema inteiro, sem olhar
    # quem escreveu — então, quando a própria pessoa enviava uma mensagem,
    # o próximo polling deste MESMO usuário via /sync via o marcador subir
    # e concluía (erradamente) "chegou mensagem nova", disparando o toast e
    # a notificação do navegador para quem tinha acabado de escrever. A
    # tentativa de contornar isso só no front-end (chamar /sync de novo logo
    # após enviar, torcendo para ganhar a corrida do próximo poll de 6s) era
    # frágil. Calculando aqui, por usuário, "qual foi a última mensagem que
    # NÃO fui eu que escrevi" resolve na raiz: o próprio autor nunca é
    # notificado da própria mensagem, não importa o timing do polling.
    ultima_mensagem = (
        db.session.query(func.max(ChatMessage.id))
        .filter(ChatMessage.user_id != current_user.id)
        .scalar()
    )
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
