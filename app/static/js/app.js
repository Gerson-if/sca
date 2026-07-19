/**
 * SCA — Sistema de Cidades e Avisos
 * Front-end (Alpine.js) — consome a API Flask em /api/*.
 *
 * Este arquivo é carregado de forma síncrona (sem `defer`) logo antes do
 * fechamento de </body>, para que `app()` já exista no escopo global
 * quando o Alpine (carregado com `defer` no <head>) inicializar e avaliar
 * `x-data="app()"`.
 */
const API_BASE = '/api';

async function apiFetch(path, options = {}) {
    const opts = {
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
    };
    if (opts.method && opts.method !== 'GET') {
        opts.headers['X-CSRFToken'] = window.__csrfToken || '';
    }
    const resp = await fetch(API_BASE + path, opts);
    let body = null;
    try { body = await resp.json(); } catch (e) { /* sem corpo JSON */ }
    if (!resp.ok) {
        const msg = (body && body.error) || 'Ocorreu um erro inesperado. Tente novamente.';
        const erro = new Error(msg);
        erro.httpStatus = resp.status;
        erro.data = body;
        throw erro;
    }
    return body;
}

// Upload multipart (não usa JSON.stringify nem Content-Type manual: o
// browser define o boundary do multipart automaticamente).
async function apiUpload(path, formData) {
    const resp = await fetch(API_BASE + path, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': window.__csrfToken || '' },
        body: formData,
    });
    let body = null;
    try { body = await resp.json(); } catch (e) { /* sem corpo JSON */ }
    if (!resp.ok) {
        const msg = (body && body.error) || 'Falha ao enviar arquivo.';
        throw new Error(msg);
    }
    return body;
}

function app() {
    return {
        // -------------------- NAVEGAÇÃO / SESSÃO --------------------
        page: 'landing', // 'landing' | 'login' | 'public' | 'admin'
        loggedIn: false,
        usuarioAtual: { id: null, username: '', nome: '', fotoUrl: null, tema: 'escuro', role: '', status: '' },

        // -------------------- PERFIL (próprio usuário) --------------------
        modalPerfilAberto: false,
        perfilTab: 'dados', // 'dados' | 'senha' | 'sessoes'
        perfilForm: { nome: '' },
        senhaForm: { senhaAtual: '', novaSenha: '', confirmarSenha: '' },
        formErrorPerfil: '',
        formErrorSenha: '',
        enviandoFotoPerfil: false,
        salvandoPerfil: false,
        sessoesAtivas: [],
        carregandoSessoes: false,

        // -------------------- SINCRONIZAÇÃO EM TEMPO REAL (polling) --------------------
        syncTimer: null,
        ultimaSync: { avisos: null, cidades: null, chatUltimoId: 0, usuarios: null },
        notificacoesPermitidas: false,

        contaPendente: false,
        contaReprovada: false,

        loginModo: 'entrar', // 'entrar' | 'cadastrar'
        loginUser: '',
        loginPass: '',
        loginError: '',
        // Desmarcado por padrão: em computador/navegador compartilhado, a
        // sessão deve morrer ao fechar o navegador. Só vira True quando a
        // própria pessoa opta por "manter conectado" (dispositivo pessoal).
        manterConectado: false,
        // Trava contra duplo-clique/duplo-envio do formulário: sem isso,
        // duas chamadas de /auth/login concorrentes usam o MESMO token CSRF
        // (obtido uma vez ao carregar a página); a primeira que responde já
        // recria a sessão no servidor, e a segunda cai com "token inválido"
        // mesmo com a senha correta — era a origem dos "erros de tokens".
        enviandoLogin: false,
        enviandoRegistro: false,
        showPass: false,

        registroUser: '',
        registroPass: '',
        registroErro: '',
        registroSucesso: '',

        searchQuery: '',
        publicTab: 'cidades', // 'cidades' | 'chat'

        adminTab: 'cidades',

        cidades: [],
        avisos: [],

        // -------------------- CONFIGURAÇÃO DA LANDING PAGE --------------------
        // Pública (não exige login) — é o que qualquer visitante vê antes de
        // entrar no sistema. Editável pelo admin na aba "Página Inicial".
        configuracaoSite: {
            nomeEmpresa: 'SCA Control',
            slogan: 'Sistema de Cidades e Avisos',
            descricao: '',
            tipoFundo: 'nenhum',
            imagemFundoUrl: null,
            videoFundoUrl: null,
            logoUrl: null,
            corDestaque: '#4f46e5'
        },
        configForm: { nomeEmpresa: '', slogan: '', descricao: '', tipoFundo: 'nenhum', imagemFundoUrl: '', videoFundoUrl: '', logoUrl: '', corDestaque: '#4f46e5' },
        formErrorConfig: '',
        enviandoMidiaSite: false,

        // -------------------- PERSONALIZAÇÃO DOS CARDS DAS CIDADES --------------------
        // Rótulos (textos) e estilo visual, aplicados automaticamente em
        // TODOS os cards — nunca altera os dados cadastrados, só como são
        // exibidos/nomeados. Editável pelo admin na aba "Personalização".
        rotulosCards: {
            perfil: 'Perfil', matriz: 'Matriz', filial: 'Filial',
            prazo: 'Prazo de O.S', semPrazo: 'Sem prazo definido',
            regraHoras: 'Regra de Horas', observacao: 'Observação',
            tecnicosFimSemana: 'Técnicos no Fim de Semana',
            aberturaFimSemana: 'Abertura no Fim de Semana',
            aberturaNormal: 'Normal', aberturaEmergencia: 'Somente Urgências', aberturaFechado: 'Fechado',
            plantonista: 'Plantonista', plantonistaAuto: 'Plantonista Ativo (Modo Auto)',
            situacaoNoPrazo: 'No Prazo', situacaoAtencao: 'Atenção', situacaoAtrasado: 'Atrasado',
            mensagemAutoLimitado: 'Agendamentos limitados para o período atual',
            mensagemAutoLiberadoTitulo: 'Canal liberado e ilimitado',
            mensagemAutoLiberadoDetalhe: 'Agendamento sem restrições de abertura.',
        },
        estiloCards: { tamanhoFonte: 'md', espacamento: 'normal', largura: 'md', colunas: 'auto', campos: ['clima', 'prazo', 'regraHoras', 'plantao', 'observacao', 'mensagemAutomatica'] },
        camposDisponiveis: [
            { chave: 'clima', label: 'Clima da Região', icone: 'fa-cloud-sun' },
            { chave: 'prazo', label: 'Prazo / Situação Operacional', icone: 'fa-hourglass-half' },
            { chave: 'regraHoras', label: 'Regra de Horas', icone: 'fa-gear' },
            { chave: 'plantao', label: 'Plantão Fim de Semana', icone: 'fa-user-shield' },
            { chave: 'observacao', label: 'Observação', icone: 'fa-note-sticky' },
            { chave: 'mensagemAutomatica', label: 'Mensagem Automática (rodapé)', icone: 'fa-robot' },
        ],
        rotulosCardsForm: {},
        estiloCardsForm: {},
        salvandoPersonalizacao: false,
        formErrorPersonalizacao: '',

        // -------------------- CLIMA (carregado por cidade) --------------------
        climaPorCidade: {},

        // -------------------- CARROSSEL DE AVISOS --------------------
        carrosselIndex: 0,
        carrosselTimer: null,

        // -------------------- DETALHE DA CIDADE (modal público) --------------------
        detalheCidadeAberto: false,
        cidadeDetalhe: null,

        modalCidadeAberta: false,
        modalAvisoAberto: false,
        formErrorCidade: '',
        formErrorAviso: '',
        enviandoImagem: false,

        chartCidadesInst: null,
        chartAvisosInst: null,

        cidadeForm: {
            id: null,
            nome: '',
            perfil: 'matriz',
            modoPrazo: 'semData',
            prazoInicio: '',
            prazoFim: '',
            regraHoras: '',
            observacao: '',
            tecnicosFimSemana: false,
            tipoAberturaFimSemana: 'normal',
            plantonistaFDS: '',
            modoAutoPlantonista: false,
            imagemUrl: ''
        },
        editandoCidade: false,
        salvandoCidade: false,

        avisoForm: {
            id: null,
            titulo: '',
            descricao: '',
            tipo: 'informativo',
            imagemUrl: null,
            modoDuracao: 'dias',
            inicio: '',
            fim: '',
            duracaoHoras: 2
        },
        editandoAviso: false,
        enviandoImagemAviso: false,
        salvandoAviso: false,

        // -------------------- USUÁRIOS (admin) --------------------
        usuarios: [],
        usuariosFiltro: 'todos',
        usuarioEditandoId: null,
        usuarioEdicaoForm: { username: '', password: '', role: '' },
        modalNovoUsuarioAberto: false,
        novoUsuarioForm: { username: '', password: '', role: 'usuario' },
        formErrorNovoUsuario: '',
        enviandoNovoUsuario: false,

        // -------------------- CHAT INTERNO --------------------
        chatMensagens: [],
        novaMensagemChat: '',
        mensagemEditandoId: null,
        mensagemEditandoTexto: '',
        chatTimer: null,
        // Modo da conversa: null = chat geral da equipe; um objeto de
        // usuário = conversa privada (direct message) com essa pessoa.
        chatConversaCom: null,
        chatUsuarios: [],
        mostrarListaUsuariosChat: false,
        enviandoMensagemChat: false,
        chatFlutuanteAberto: false,
        chatNaoLidas: 0,

        // -------------------- GRUPOS DE CHAT (canais) --------------------
        chatGrupos: [],
        chatGrupoAtual: null,
        modalNovoGrupoAberto: false,
        novoGrupoForm: { nome: '', descricao: '', icone: 'fa-users', cor: 'indigo', membrosIds: [] },
        formErrorNovoGrupo: '',
        enviandoNovoGrupo: false,
        editandoGrupoId: null, // se preenchido, o modal "novo grupo" vira "editar grupo"
        modalMembrosGrupoAberto: false,
        grupoMembrosAtual: [],
        grupoParaGerenciar: null,
        iconesGrupoDisponiveis: [
            'fa-users', 'fa-hashtag', 'fa-comments', 'fa-bullhorn', 'fa-briefcase',
            'fa-wrench', 'fa-truck-medical', 'fa-city', 'fa-star', 'fa-fire',
            'fa-shield-halved', 'fa-code', 'fa-chart-line', 'fa-headset', 'fa-map-location-dot',
        ],
        coresGrupoDisponiveis: ['indigo', 'blue', 'emerald', 'amber', 'rose', 'violet', 'cyan', 'slate'],
        perfilRapido: null, // usuário sendo mostrado no popover de perfil rápido do chat

        dataHora: '',

        // -------------------- NOTIFICAÇÕES E CONFIRMAÇÕES --------------------
        toast: { show: false, mensagem: '', tipo: 'sucesso', icone: 'fa-circle-check' },
        toastTimeout: null,
        confirmacao: { show: false, titulo: '', mensagem: '', acao: null },

        async init() {
            // Antes até de saber se há sessão: aplica um tema "de visitante"
            // salvo localmente, pra não piscar claro->escuro na tela de login.
            this.aplicarTema(localStorage.getItem('sca_tema_visitante') || 'escuro');

            await this.obterCsrfToken();
            await this.carregarConfiguracaoSite();
            await this.verificarSessao();

            this.atualizarDataHora();
            setInterval(() => this.atualizarDataHora(), 1000);

            // Carrossel de avisos: avança automaticamente. Intervalo maior
            // (10s) dá tempo de ler avisos com texto mais longo antes de
            // trocar de slide.
            this.carrosselTimer = setInterval(() => {
                const total = this.avisosPublicos().length;
                if (total > 1) this.carrosselIndex = (this.carrosselIndex + 1) % total;
            }, 10000);

            // Chat: consulta a cada 4s quando a aba de chat está visível.
            this.chatTimer = setInterval(() => {
                const vendoChatEmAba = this.page === 'public' && this.publicTab === 'chat';
                if (this.podeVerAreaPublica() && (vendoChatEmAba || this.chatFlutuanteAberto)) {
                    this.carregarChat(true);
                }
            }, 4000);

            setInterval(() => {
                if (this.podeVerAreaPublica()) {
                    this.carregarAvisos();
                }
                this.renderizarOuAtualizarGraficos();
            }, 30000);

            // Sincronização quase em tempo real: a cada poucos segundos,
            // pergunta ao servidor "algo mudou?" e, se sim, recarrega só a
            // seção afetada e avisa a pessoa (toast + notificação do
            // navegador, se permitida). Ver app/api/sync.py para o porquê
            // de ser polling em vez de WebSocket.
            this.syncTimer = setInterval(() => this.verificarSincronizacao(), 6000);
        },

        // -------------------- INTEGRAÇÃO COM A API --------------------
        async obterCsrfToken() {
            try {
                const data = await apiFetch('/auth/csrf-token');
                window.__csrfToken = data.csrfToken;
            } catch (e) { /* segue sem token; rotas GET não exigem */ }
        },

        // Rota pública, sem autenticação — alimenta a landing page e o
        // rodapé/cabeçalho com a identidade visual definida pelo admin.
        async carregarConfiguracaoSite() {
            try {
                this.configuracaoSite = await apiFetch('/configuracao');
            } catch (e) { /* mantém os valores padrão se falhar */ }
        },

        // Exige sessão aprovada (é o que rotula/estiliza os cards que a
        // pessoa vê) — só a edição é restrita ao admin.
        async carregarConfiguracaoCards() {
            try {
                const data = await apiFetch('/configuracao/cards');
                this.rotulosCards = data.rotulos;
                this.estiloCards = data.estilo;
            } catch (e) { /* mantém os rótulos padrão se falhar */ }
        },

        podeVerAreaPublica() {
            return this.loggedIn && (this.usuarioAtual.role === 'admin' || this.usuarioAtual.status === 'aprovado');
        },

        async verificarSessao() {
            try {
                const data = await apiFetch('/auth/me');
                this.loggedIn = !!data.loggedIn;
                if (this.loggedIn) {
                    // Só existe sessão autenticada para admin ou usuário já
                    // aprovado — o backend nunca cria sessão para contas
                    // pendentes/reprovadas (ver /api/auth/login).
                    this.usuarioAtual = data.user;
                    this.loginUser = data.user.username;
                    this.aplicarTema(data.user.tema);
                    if (this.podeVerAreaPublica()) {
                        this.page = data.user.role === 'admin' ? 'admin' : 'public';
                        await this.carregarCidades();
                        await this.carregarAvisos();
                        await this.carregarConfiguracaoCards();
                        await this.atualizarMarcadoresSync();
                        this.pedirPermissaoNotificacao();
                        if (data.user.role === 'admin') {
                            this.$nextTick(() => this.renderizarOuAtualizarGraficos());
                        }
                    }
                }
                // Visitante sem sessão válida: permanece na landing page
                // (valor padrão de `page`), sem nenhuma chamada a rotas
                // internas do sistema.
            } catch (e) { this.loggedIn = false; }
        },

        async carregarCidades() {
            try {
                this.cidades = await apiFetch('/cidades');
                this.cidades.forEach(c => this.carregarClima(c.id));
            } catch (e) {
                this.notificar('Não foi possível carregar as cidades.', 'erro');
            }
        },

        async carregarAvisos() {
            try {
                this.avisos = await apiFetch('/avisos');
            } catch (e) {
                this.notificar(`Não foi possível carregar os avisos (${e.message}).`, 'erro');
            }
        },

        async carregarClima(cidadeId) {
            try {
                const data = await apiFetch(`/cidades/${cidadeId}/clima`);
                this.climaPorCidade[cidadeId] = data;
            } catch (e) {
                this.climaPorCidade[cidadeId] = { disponivel: false };
            }
        },

        // -------------------- NAVEGAÇÃO --------------------
        goLanding() {
            this.destruirGraficos();
            this.page = 'landing';
        },
        goPublic() {
            // Evita o bug de gráficos "mortos": ao sair do admin, o <template
            // x-if="page === 'admin'"> remove os <canvas> do DOM, mas as
            // instâncias do Chart.js continuavam vivas em memória e quebravam
            // ao tentar atualizar um canvas que não existe mais. Destruímos
            // aqui para forçar recriação limpa na próxima vez que abrir o admin.
            this.destruirGraficos();
            // Visitante sem sessão aprovada nunca vê a área pública — cai
            // sempre na landing page, sem tentar carregar dados do sistema.
            if (!this.podeVerAreaPublica()) {
                this.page = 'landing';
                return;
            }
            this.page = 'public';
            if (this.cidades.length === 0) {
                this.carregarCidades();
                this.carregarAvisos();
            }
        },
        goAdmin() {
            if (this.usuarioAtual.role !== 'admin') return;
            this.page = 'admin';
            this.carregarCidades();
            this.carregarAvisos();
            this.carregarUsuarios();
            this.configForm = { ...this.configuracaoSite };
            this.$nextTick(() => this.renderizarOuAtualizarGraficos());
        },
        goLogin() {
            this.loginError = '';
            this.loginModo = 'entrar';
            this.page = 'login';
        },
        setAdminTab(aba) {
            this.adminTab = aba;
            if (aba === 'usuarios') this.carregarUsuarios();
            if (aba === 'landing') this.configForm = { ...this.configuracaoSite };
            if (aba === 'personalizacao') this.abrirPersonalizacaoCards();
            this.$nextTick(() => this.renderizarOuAtualizarGraficos());
        },

        destruirGraficos() {
            if (this.chartCidadesInst) { this.chartCidadesInst.destroy(); this.chartCidadesInst = null; }
            if (this.chartAvisosInst) { this.chartAvisosInst.destroy(); this.chartAvisosInst = null; }
        },

        // -------------------- FILTRO DE PESQUISA (CIDADES) --------------------
        cidadesFiltradas() {
            if (!this.searchQuery.trim()) {
                return this.cidades;
            }
            const q = this.searchQuery.toLowerCase();
            return this.cidades.filter(c =>
                c.nome.toLowerCase().includes(q) ||
                c.perfil.toLowerCase().includes(q) ||
                (c.regraHoras && c.regraHoras.toLowerCase().includes(q))
            );
        },

        isFimDeSemana() {
            const d = new Date().getDay();
            return d === 0 || d === 6;
        },

        // -------------------- SESSÃO (via API Flask-Login) --------------------
        async doLogin() {
            if (this.enviandoLogin) return; // já tem uma requisição de login em andamento
            if (!this.loginUser.trim() || !this.loginPass.trim()) {
                this.loginError = 'Preencha usuário e senha para acessar.';
                return;
            }
            this.loginError = '';
            this.contaPendente = false;
            this.contaReprovada = false;
            this.enviandoLogin = true;
            try {
                const resp = await apiFetch('/auth/login', {
                    method: 'POST',
                    body: JSON.stringify({
                        username: this.loginUser,
                        password: this.loginPass,
                        manterConectado: this.manterConectado,
                    }),
                });
                // A sessão foi recriada no backend (mitigação de fixação de
                // sessão); o token de CSRF antigo não vale mais — usamos o
                // novo que já vem na resposta do login.
                if (resp.csrfToken) window.__csrfToken = resp.csrfToken;

                this.loggedIn = true;
                this.usuarioAtual = resp.user;
                this.aplicarTema(resp.user.tema);
                this.loginPass = '';
                this.page = resp.user.role === 'admin' ? 'admin' : 'public';
                await this.carregarCidades();
                await this.carregarAvisos();
                await this.carregarConfiguracaoCards();
                await this.atualizarMarcadoresSync();
                this.pedirPermissaoNotificacao();
                if (resp.user.role === 'admin') {
                    await this.carregarUsuarios();
                    this.configForm = { ...this.configuracaoSite };
                    this.$nextTick(() => this.renderizarOuAtualizarGraficos());
                }
            } catch (e) {
                // Contas pendentes/reprovadas nunca ganham sessão no backend
                // (ver /api/auth/login) — o front só mostra a telinha certa,
                // sem tratar isso como "logado".
                if (e.data && e.data.status === 'pendente') {
                    this.contaPendente = true;
                    this.loginUser = e.data.username || this.loginUser;
                } else if (e.data && e.data.status === 'reprovado') {
                    this.contaReprovada = true;
                } else {
                    this.loginError = e.message;
                }
            } finally {
                this.enviandoLogin = false;
            }
        },

        async doRegistrar() {
            if (this.enviandoRegistro) return; // trava contra duplo-envio
            this.registroErro = '';
            this.registroSucesso = '';
            if (!this.registroUser.trim() || !this.registroPass.trim()) {
                this.registroErro = 'Preencha usuário e senha.';
                return;
            }
            try {
                this.enviandoRegistro = true;
                const resp = await apiFetch('/auth/registrar', {
                    method: 'POST',
                    body: JSON.stringify({ username: this.registroUser, password: this.registroPass }),
                });
                this.registroSucesso = resp.message;
                this.registroUser = '';
                this.registroPass = '';
            } catch (e) {
                this.registroErro = e.message;
            } finally {
                this.enviandoRegistro = false;
            }
        },

        async logout() {
            try {
                const resp = await apiFetch('/auth/logout', { method: 'POST' });
                if (resp && resp.csrfToken) window.__csrfToken = resp.csrfToken;
            } catch (e) { /* ignora */ }
            this.loggedIn = false;
            this.usuarioAtual = { id: null, username: '', nome: '', fotoUrl: null, tema: 'escuro', role: '', status: '' };
            this.contaPendente = false;
            this.contaReprovada = false;
            this.loginUser = '';
            this.loginPass = '';
            this.manterConectado = false;
            this.destruirGraficos();
            this.page = 'landing';
            this.cidades = [];
            this.avisos = [];
            this.chatMensagens = [];
            this.sessoesAtivas = [];
            // Ao sair, volta pro tema padrão do "visitante" — não deixa o
            // tema pessoal de quem acabou de sair aplicado num computador
            // compartilhado para a próxima pessoa que abrir o navegador.
            this.aplicarTema('escuro');
        },

        // Sai das telas de "aguardando aprovação"/"reprovado" — nenhuma
        // sessão foi criada nesses casos (ver /api/auth/login), então basta
        // resetar o estado local do formulário, sem chamar o backend.
        voltarLogin() {
            this.contaPendente = false;
            this.contaReprovada = false;
            this.loginUser = '';
            this.loginPass = '';
            this.manterConectado = false;
            this.loginModo = 'entrar';
            this.page = 'landing';
        },

        // -------------------- FORMATAÇÃO DE DATAS --------------------
        formatarData(dataStr, comHora = false) {
            if (!dataStr) return '';
            const [dataParte, horaParte] = dataStr.split('T');
            const [ano, mes, dia] = dataParte.split('-');
            let saida = `${dia}/${mes}/${ano}`;
            if (comHora && horaParte) saida += ` às ${horaParte}`;
            return saida;
        },

        // -------------------- PRAZOS DE CIDADES --------------------
        paraTimestamp(str, fimDoDia = false) {
            if (!str) return null;
            if (str.includes('T')) return new Date(str).getTime();
            return new Date(str + (fimDoDia ? 'T23:59:59' : 'T00:00:00')).getTime();
        },

        obterPorcentagemEntreDatas(inicioStr, fimStr) {
            const inicio = this.paraTimestamp(inicioStr, false);
            const fim = this.paraTimestamp(fimStr, true);
            if (inicio === null || fim === null) return 0;
            const agora = new Date().getTime();

            if (fim <= inicio) return 100;
            if (agora < inicio) return 0;
            if (agora > fim) return 100;

            const total = fim - inicio;
            const decorrido = agora - inicio;
            const progresso = Math.round((decorrido / total) * 100);
            return Math.min(Math.max(progresso, 0), 100);
        },

        obterPorcentagemPrazo(inicioStr, fimStr) {
            return this.obterPorcentagemEntreDatas(inicioStr, fimStr);
        },

        obterRangeAviso(aviso) {
            if (aviso.modoDuracao === 'horas') {
                const inicio = new Date(aviso.inicio);
                const fim = new Date(inicio.getTime() + (Number(aviso.duracaoHoras) || 0) * 3600000);
                return { inicio, fim };
            }
            const inicio = new Date(aviso.inicio + 'T00:00:00');
            const fim = new Date(aviso.fim + 'T23:59:59');
            return { inicio, fim };
        },

        obterPorcentagemAviso(aviso) {
            const { inicio, fim } = this.obterRangeAviso(aviso);
            const agora = new Date().getTime();
            const inicioMs = inicio.getTime();
            const fimMs = fim.getTime();

            if (fimMs <= inicioMs) return 100;
            if (agora < inicioMs) return 0;
            if (agora > fimMs) return 100;

            const progresso = Math.round(((agora - inicioMs) / (fimMs - inicioMs)) * 100);
            return Math.min(Math.max(progresso, 0), 100);
        },

        obterCorBarraProgresso(porcentagem) {
            if (porcentagem < 60) return 'bg-blue-500';
            if (porcentagem < 85) return 'bg-amber-500';
            return 'bg-rose-500';
        },

        // -------------------- SITUAÇÃO DA CIDADE (texto personalizável) --------------------
        rotuloSituacao(porcentagem) {
            if (porcentagem < 60) return this.rotulosCards.situacaoNoPrazo;
            if (porcentagem < 85) return this.rotulosCards.situacaoAtencao;
            return this.rotulosCards.situacaoAtrasado;
        },
        corSituacao(porcentagem) {
            if (porcentagem < 60) return 'text-blue-400 bg-blue-500/10';
            if (porcentagem < 85) return 'text-amber-400 bg-amber-500/10';
            return 'text-rose-400 bg-rose-500/10';
        },

        // -------------------- ESTILO DOS CARDS (aplicado globalmente) --------------------
        classeFonteCards() {
            return { sm: 'text-xs', md: 'text-sm', lg: 'text-base' }[this.estiloCards.tamanhoFonte] || 'text-sm';
        },
        classeEspacamentoCards() {
            return { compacto: 'gap-3', normal: 'gap-5', espacoso: 'gap-8' }[this.estiloCards.espacamento] || 'gap-5';
        },
        classePaddingCards() {
            return { compacto: 'p-3', normal: 'p-5', espacoso: 'p-7' }[this.estiloCards.espacamento] || 'p-5';
        },
        classeGridCards() {
            if (this.estiloCards.colunas && this.estiloCards.colunas !== 'auto') {
                return { '1': 'grid-cols-1', '2': 'sm:grid-cols-2', '3': 'sm:grid-cols-2 lg:grid-cols-3', '4': 'sm:grid-cols-2 lg:grid-cols-4' }[this.estiloCards.colunas] || 'sm:grid-cols-2 lg:grid-cols-3';
            }
            return 'sm:grid-cols-2 lg:grid-cols-3'; // 'auto': padrão responsivo atual
        },
        classeLarguraCards() {
            return { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-lg', xl: 'max-w-xl' }[this.estiloCards.largura] || '';
        },
        campoVisivel(chave, origemForm = false) {
            const estilo = origemForm ? this.estiloCardsForm : this.estiloCards;
            return Array.isArray(estilo.campos) && estilo.campos.includes(chave);
        },

        // -------------------- MONTAGEM DOS CARDS (builder) --------------------
        alternarCampoForm(chave) {
            const lista = this.estiloCardsForm.campos || [];
            const idx = lista.indexOf(chave);
            if (idx === -1) {
                this.estiloCardsForm.campos = [...lista, chave];
            } else {
                this.estiloCardsForm.campos = lista.filter(c => c !== chave);
            }
        },
        moverCampoForm(chave, direcao) {
            const lista = [...(this.estiloCardsForm.campos || [])];
            const idx = lista.indexOf(chave);
            if (idx === -1) return; // campo oculto não tem posição para mover
            const novoIdx = idx + direcao;
            if (novoIdx < 0 || novoIdx >= lista.length) return;
            [lista[idx], lista[novoIdx]] = [lista[novoIdx], lista[idx]];
            this.estiloCardsForm.campos = lista;
        },
        // Cidade de exemplo só para a pré-visualização ao vivo — nunca é
        // salva nem enviada ao servidor, existe apenas no navegador.
        cidadeExemploPreview: {
            nome: 'Cidade Exemplo', perfil: 'matriz',
            observacao: 'Esta é uma observação de exemplo para você ver como o texto aparece no card.',
            modoPrazo: 'periodo', prazoInicio: '2026-07-10', prazoFim: '2026-07-25',
            regraHoras: 'Modo Normal (Fluxo Livre)',
            tecnicosFimSemana: true, modoAutoPlantonista: true, plantonistaFDS: '',
            tipoAberturaFimSemana: 'normal',
        },

        async salvarPersonalizacaoCards() {
            if (this.salvandoPersonalizacao) return;
            this.formErrorPersonalizacao = '';
            this.salvandoPersonalizacao = true;
            try {
                const atualizado = await apiFetch('/configuracao/cards', {
                    method: 'PUT',
                    body: JSON.stringify({ rotulos: this.rotulosCardsForm, estilo: this.estiloCardsForm }),
                });
                this.rotulosCards = atualizado.rotulos;
                this.estiloCards = atualizado.estilo;
                this.notificar('Personalização dos cards salva — já aplicada em todos eles.', 'sucesso');
            } catch (e) {
                this.formErrorPersonalizacao = e.message;
            } finally {
                this.salvandoPersonalizacao = false;
            }
        },
        abrirPersonalizacaoCards() {
            this.rotulosCardsForm = { ...this.rotulosCards };
            this.estiloCardsForm = { ...this.estiloCards, campos: [...(this.estiloCards.campos || [])] };
            this.formErrorPersonalizacao = '';
        },

        // -------------------- STATUS DE PLANTÃO --------------------
        rotuloAbertura(tipo) {
            if (tipo === 'emergencia') return this.rotulosCards.aberturaEmergencia;
            if (tipo === 'fechado') return this.rotulosCards.aberturaFechado;
            return this.rotulosCards.aberturaNormal;
        },

        // -------------------- AVISOS VISÍVEIS AO PÚBLICO --------------------
        avisosPublicos() {
            return this.avisos.filter(a => a.status !== 'Expirado');
        },

        // -------------------- DETALHE DA CIDADE --------------------
        abrirDetalheCidade(cidade) {
            this.cidadeDetalhe = cidade;
            this.detalheCidadeAberto = true;
            if (!this.climaPorCidade[cidade.id]) this.carregarClima(cidade.id);
        },
        fecharDetalheCidade() {
            this.detalheCidadeAberto = false;
            this.cidadeDetalhe = null;
        },

        // -------------------- NOTIFICAÇÕES (TOAST) --------------------
        notificar(mensagem, tipo = 'sucesso') {
            const icones = { sucesso: 'fa-circle-check', erro: 'fa-circle-exclamation', aviso: 'fa-triangle-exclamation' };
            if (this.toastTimeout) clearTimeout(this.toastTimeout);
            this.toast = { show: true, mensagem, tipo, icone: icones[tipo] || 'fa-circle-check' };
            this.toastTimeout = setTimeout(() => { this.toast.show = false; }, 3500);
        },

        // -------------------- CONFIRMAÇÃO DE AÇÕES SENSÍVEIS --------------------
        pedirConfirmacao(titulo, mensagem, acao) {
            this.confirmacao = { show: true, titulo, mensagem, acao };
        },
        confirmarAcao() {
            if (typeof this.confirmacao.acao === 'function') this.confirmacao.acao();
            this.confirmacao = { show: false, titulo: '', mensagem: '', acao: null };
        },
        cancelarConfirmacao() {
            this.confirmacao = { show: false, titulo: '', mensagem: '', acao: null };
        },

        // -------------------- MODAIS CIDADE --------------------
        abrirModalCidade() {
            this.cancelarEdicaoCidade();
            this.modalCidadeAberta = true;
        },
        fecharModalCidade() {
            this.modalCidadeAberta = false;
            this.cancelarEdicaoCidade();
        },

        async enviarImagemCidade(evento) {
            const arquivo = evento.target.files[0];
            if (!arquivo) return;
            this.enviandoImagem = true;
            try {
                const formData = new FormData();
                formData.append('arquivo', arquivo);
                const resp = await apiUpload('/uploads/imagem', formData);
                this.cidadeForm.imagemUrl = resp.url;
                this.notificar('Imagem enviada e otimizada com sucesso.', 'sucesso');
            } catch (e) {
                this.notificar(e.message, 'erro');
            } finally {
                this.enviandoImagem = false;
                evento.target.value = '';
            }
        },

        // -------------------- CONFIGURAÇÃO DA LANDING PAGE (admin) --------------------
        async enviarLogoSite(evento) {
            const arquivo = evento.target.files[0];
            if (!arquivo) return;
            this.enviandoMidiaSite = true;
            try {
                const formData = new FormData();
                formData.append('arquivo', arquivo);
                const resp = await apiUpload('/uploads/imagem', formData);
                this.configForm.logoUrl = resp.url;
                this.notificar('Logotipo enviado com sucesso.', 'sucesso');
            } catch (e) {
                this.notificar(e.message, 'erro');
            } finally {
                this.enviandoMidiaSite = false;
                evento.target.value = '';
            }
        },

        async enviarImagemFundoSite(evento) {
            const arquivo = evento.target.files[0];
            if (!arquivo) return;
            this.enviandoMidiaSite = true;
            try {
                const formData = new FormData();
                formData.append('arquivo', arquivo);
                const resp = await apiUpload('/uploads/imagem', formData);
                this.configForm.imagemFundoUrl = resp.url;
                this.notificar('Imagem de fundo enviada e otimizada com sucesso.', 'sucesso');
            } catch (e) {
                this.notificar(e.message, 'erro');
            } finally {
                this.enviandoMidiaSite = false;
                evento.target.value = '';
            }
        },

        async enviarVideoFundoSite(evento) {
            const arquivo = evento.target.files[0];
            if (!arquivo) return;
            this.enviandoMidiaSite = true;
            try {
                const formData = new FormData();
                formData.append('arquivo', arquivo);
                const resp = await apiUpload('/uploads/video', formData);
                this.configForm.videoFundoUrl = resp.url;
                this.notificar('Vídeo enviado com sucesso.', 'sucesso');
            } catch (e) {
                this.notificar(e.message, 'erro');
            } finally {
                this.enviandoMidiaSite = false;
                evento.target.value = '';
            }
        },

        async salvarConfiguracaoSite() {
            this.formErrorConfig = '';
            if (!this.configForm.nomeEmpresa.trim()) {
                this.formErrorConfig = 'Informe o nome da empresa.';
                return;
            }
            try {
                this.configuracaoSite = await apiFetch('/configuracao', {
                    method: 'PUT',
                    body: JSON.stringify(this.configForm),
                });
                this.configForm = { ...this.configuracaoSite };
                this.notificar('Página inicial atualizada com sucesso.', 'sucesso');
            } catch (e) {
                this.formErrorConfig = e.message;
            }
        },

        // -------------------- MODAIS AVISO --------------------
        abrirModalAviso() {
            this.cancelarEdicaoAviso();
            this.modalAvisoAberto = true;
        },
        fecharModalAviso() {
            this.modalAvisoAberto = false;
            this.cancelarEdicaoAviso();
        },

        previsaoFimHoras() {
            if (!this.avisoForm.duracaoHoras) return '—';
            // A contagem sempre começa no instante em que o aviso for salvo
            // (calculado pelo servidor) — aqui é só uma prévia usando o
            // relógio local, que deve bater com poucos segundos de diferença.
            const inicio = new Date();
            const fim = new Date(inicio.getTime() + Number(this.avisoForm.duracaoHoras) * 3600000);
            const pad = n => String(n).padStart(2, '0');
            return `${pad(fim.getDate())}/${pad(fim.getMonth() + 1)}/${fim.getFullYear()} às ${pad(fim.getHours())}:${pad(fim.getMinutes())}`;
        },

        // -------------------- GRÁFICOS (CHART.JS) --------------------
        renderizarOuAtualizarGraficos() {
            if (!this.loggedIn || this.page !== 'admin') return;
            // Trava simples contra chamadas sobrepostas: se duas ações (ex.:
            // excluir um aviso + a sincronização automática) disparassem
            // isso quase ao mesmo tempo, uma segunda chamada de
            // chart.update() no meio da animação da primeira é o que
            // corrompe o estado interno do Chart.js e gera o erro
            // "Cannot set properties of undefined (setting 'fullSize')".
            if (this._atualizandoGraficos) return;
            this._atualizandoGraficos = true;

            try {
                const matrizes = this.cidades.filter(c => c.perfil === 'matriz').length;
                const filiais = this.cidades.filter(c => c.perfil === 'filial').length;

                const ativos = this.avisos.filter(a => a.status === 'Ativo').length;
                const aguardando = this.avisos.filter(a => a.status === 'Aguardando').length;
                const expirados = this.avisos.filter(a => a.status === 'Expirado').length;

                const fontColor = '#94a3b8';
                Chart.defaults.color = fontColor;
                Chart.defaults.font.family = "'Inter', sans-serif";

                // Se o canvas não estiver de fato visível/renderizado
                // (offsetParent null = display:none em algum ancestral, ou
                // o elemento foi trocado por outro depois de um x-if),
                // qualquer tentativa de desenhar deixa o Chart.js com
                // dimensões zero — origem clássica desse erro. Melhor
                // pular silenciosamente; a próxima chamada (ao voltar pra
                // essa tela) redesenha normalmente.
                const visivel = (el) => !!el && el.offsetParent !== null;

                const ctxCidades = document.getElementById('chartCidades');
                if (visivel(ctxCidades)) {
                    // Sempre destrói e recria em vez de reaproveitar a
                    // instância antiga com .update(): se o canvas foi
                    // substituído no DOM (Alpine recria o bloco inteiro do
                    // admin ao trocar de página) a instância antiga ainda
                    // aponta pro canvas MORTO, e atualizar isso é
                    // exatamente o que gera o erro relatado. Recriar do
                    // zero elimina essa classe inteira de bug.
                    if (this.chartCidadesInst) {
                        try { this.chartCidadesInst.destroy(); } catch (e) { /* instância já inválida, ignora */ }
                        this.chartCidadesInst = null;
                    }
                    this.chartCidadesInst = new Chart(ctxCidades, {
                        type: 'bar',
                        data: {
                            labels: ['Matriz', 'Filiais'],
                            datasets: [{
                                label: 'Quantidade',
                                data: [matrizes, filiais],
                                backgroundColor: ['#3b82f6', '#64748b'],
                                borderRadius: 8,
                                borderWidth: 0,
                                barThickness: 32
                            }]
                        },
                        options: {
                            indexAxis: 'y',
                            responsive: true,
                            maintainAspectRatio: false,
                            animation: { duration: 300 },
                            plugins: { legend: { display: false } },
                            scales: {
                                x: { grid: { color: '#1e293b' }, ticks: { precision: 0, color: fontColor } },
                                y: { grid: { display: false }, ticks: { color: fontColor } }
                            }
                        }
                    });
                }

                const ctxAvisos = document.getElementById('chartAvisos');
                if (visivel(ctxAvisos)) {
                    if (this.chartAvisosInst) {
                        try { this.chartAvisosInst.destroy(); } catch (e) { /* instância já inválida, ignora */ }
                        this.chartAvisosInst = null;
                    }
                    this.chartAvisosInst = new Chart(ctxAvisos, {
                        type: 'doughnut',
                        data: {
                            labels: ['Ativos', 'Aguardando', 'Expirados'],
                            datasets: [{
                                data: [ativos, aguardando, expirados],
                                backgroundColor: ['#10b981', '#f59e0b', '#f43f5e'],
                                borderWidth: 3,
                                borderColor: '#0f172a'
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            animation: { duration: 300 },
                            plugins: {
                                legend: {
                                    position: 'right',
                                    labels: { usePointStyle: true, boxWidth: 6, font: { size: 11 }, color: fontColor }
                                }
                            },
                            cutout: '65%'
                        }
                    });
                }
            } catch (e) {
                // Um gráfico é um "nice to have" — nunca deve derrubar a
                // ação que o disparou (ex.: excluir um aviso). Só loga.
                console.error('Falha ao desenhar gráficos:', e);
            } finally {
                this._atualizandoGraficos = false;
            }
        },

        // -------------------- CIDADES CRUD (via API) --------------------
        async salvarCidade() {
            if (this.salvandoCidade) return; // já tem um envio em andamento — ignora clique duplicado
            this.formErrorCidade = '';

            if (!this.cidadeForm.nome.trim()) {
                this.formErrorCidade = 'Informe o nome da cidade.';
                return;
            }
            if (this.cidadeForm.modoPrazo !== 'semData') {
                if (!this.cidadeForm.prazoInicio || !this.cidadeForm.prazoFim) {
                    this.formErrorCidade = 'Defina o início e o fim do prazo operacional para esta localidade.';
                    return;
                }
                if (this.cidadeForm.prazoFim < this.cidadeForm.prazoInicio) {
                    this.formErrorCidade = 'A data/hora de fim do prazo não pode ser anterior à de início.';
                    return;
                }
            }

            const eraEdicao = this.editandoCidade;
            const nomeCidade = this.cidadeForm.nome;
            this.salvandoCidade = true;
            try {
                if (eraEdicao) {
                    await apiFetch(`/cidades/${this.cidadeForm.id}`, {
                        method: 'PUT',
                        body: JSON.stringify(this.cidadeForm),
                    });
                } else {
                    await apiFetch('/cidades', {
                        method: 'POST',
                        body: JSON.stringify(this.cidadeForm),
                    });
                }
                await this.carregarCidades();
                this.fecharModalCidade();
                this.renderizarOuAtualizarGraficos();
                this.notificar(eraEdicao ? `Cidade "${nomeCidade}" atualizada com sucesso.` : `Cidade "${nomeCidade}" cadastrada com sucesso.`, 'sucesso');
            } catch (e) {
                if (e.httpStatus === 404) {
                    // Alguém mais já excluiu esta cidade enquanto o modal
                    // estava aberto — autocorrige em vez de mostrar um
                    // "erro 404" sem contexto.
                    await this.carregarCidades();
                    this.fecharModalCidade();
                    this.notificar('Esta cidade já não existe mais — ela foi removida antes que você salvasse. A lista foi atualizada.', 'aviso');
                    return;
                }
                this.formErrorCidade = e.message;
            } finally {
                this.salvandoCidade = false;
            }
        },

        editarCidade(cidade) {
            this.cidadeForm = { ...cidade };
            this.editandoCidade = true;
            this.formErrorCidade = '';
            this.modalCidadeAberta = true;
        },

        cancelarEdicaoCidade() {
            this.cidadeForm = {
                id: null,
                nome: '',
                perfil: 'matriz',
                modoPrazo: 'semData',
                prazoInicio: '',
                prazoFim: '',
                regraHoras: '',
                observacao: '',
                tecnicosFimSemana: false,
                tipoAberturaFimSemana: 'normal',
                plantonistaFDS: '',
                modoAutoPlantonista: false,
                imagemUrl: ''
            };
            this.editandoCidade = false;
            this.formErrorCidade = '';
        },

        excluirCidade(id) {
            const cidade = this.cidades.find(c => c.id === id);
            const nome = cidade ? cidade.nome : 'esta cidade';
            this.pedirConfirmacao(
                'Excluir cidade',
                `Tem certeza que deseja excluir "${nome}"? Essa ação é definitiva e não pode ser desfeita.`,
                async () => {
                    try {
                        await apiFetch(`/cidades/${id}`, { method: 'DELETE' });
                        await this.carregarCidades();
                        this.renderizarOuAtualizarGraficos();
                        this.notificar(`Cidade "${nome}" excluída com sucesso.`, 'aviso');
                    } catch (e) {
                        this.notificar(e.message, 'erro');
                    }
                }
            );
        },

        // -------------------- AVISOS CRUD (via API) --------------------
        async enviarImagemAviso(evento) {
            const arquivo = evento.target.files[0];
            if (!arquivo) return;
            this.enviandoImagemAviso = true;
            try {
                const formData = new FormData();
                formData.append('arquivo', arquivo);
                const resp = await apiUpload('/avisos/upload-imagem', formData);
                this.avisoForm.imagemUrl = resp.url;
            } catch (e) {
                this.notificar(e.message, 'erro');
            } finally {
                this.enviandoImagemAviso = false;
                evento.target.value = '';
            }
        },

        async salvarAviso() {
            if (this.salvandoAviso) return; // já tem um envio em andamento — ignora clique duplicado
            this.formErrorAviso = '';

            if (!this.avisoForm.titulo.trim()) {
                this.formErrorAviso = 'Informe o título do aviso.';
                return;
            }
            if (this.avisoForm.modoDuracao === 'dias') {
                if (!this.avisoForm.inicio || !this.avisoForm.fim) {
                    this.formErrorAviso = 'Defina as datas de início e fim da vigência.';
                    return;
                }
                if (this.avisoForm.fim < this.avisoForm.inicio) {
                    this.formErrorAviso = 'A data de fim não pode ser anterior à data de início.';
                    return;
                }
            } else {
                if (!this.avisoForm.duracaoHoras || Number(this.avisoForm.duracaoHoras) <= 0) {
                    this.formErrorAviso = 'Informe uma duração em horas maior que zero.';
                    return;
                }
            }

            const eraEdicao = this.editandoAviso;
            const tituloAviso = this.avisoForm.titulo;
            this.salvandoAviso = true;
            try {
                if (eraEdicao) {
                    await apiFetch(`/avisos/${this.avisoForm.id}`, {
                        method: 'PUT',
                        body: JSON.stringify(this.avisoForm),
                    });
                } else {
                    await apiFetch('/avisos', {
                        method: 'POST',
                        body: JSON.stringify(this.avisoForm),
                    });
                }
                await this.carregarAvisos();
                this.fecharModalAviso();
                this.renderizarOuAtualizarGraficos();
                this.notificar(eraEdicao ? `Aviso "${tituloAviso}" atualizado com sucesso.` : `Aviso "${tituloAviso}" publicado com sucesso.`, 'sucesso');
            } catch (e) {
                if (e.httpStatus === 404) {
                    // Alguém mais (ou você mesmo, em outra aba) já excluiu
                    // esse aviso enquanto este modal estava aberto. Em vez
                    // de um "erro 404" confuso, atualiza a lista e avisa.
                    await this.carregarAvisos();
                    this.fecharModalAviso();
                    this.notificar('Este aviso já não existe mais — ele foi removido antes que você salvasse. A lista foi atualizada.', 'aviso');
                    return;
                }
                this.formErrorAviso = e.message;
            } finally {
                this.salvandoAviso = false;
            }
        },

        editarAviso(aviso) {
            this.avisoForm = { ...aviso };
            this.editandoAviso = true;
            this.formErrorAviso = '';
            this.modalAvisoAberto = true;
        },

        cancelarEdicaoAviso() {
            this.avisoForm = { id: null, titulo: '', descricao: '', tipo: 'informativo', imagemUrl: null, modoDuracao: 'dias', inicio: '', fim: '', duracaoHoras: 2 };
            this.editandoAviso = false;
            this.formErrorAviso = '';
        },

        excluirAviso(id) {
            const aviso = this.avisos.find(a => a.id === id);
            const titulo = aviso ? aviso.titulo : 'este aviso';
            this.pedirConfirmacao(
                'Excluir aviso',
                `Tem certeza que deseja apagar "${titulo}" permanentemente? Essa ação é definitiva e não pode ser desfeita.`,
                async () => {
                    try {
                        await apiFetch(`/avisos/${id}`, { method: 'DELETE' });
                        await this.carregarAvisos();
                        this.renderizarOuAtualizarGraficos();
                        this.notificar(`Aviso "${titulo}" excluído com sucesso.`, 'aviso');
                    } catch (e) {
                        if (e.httpStatus === 404) {
                            await this.carregarAvisos();
                            this.notificar('Este aviso já havia sido removido por outra pessoa. A lista foi atualizada.', 'aviso');
                            return;
                        }
                        this.notificar(e.message, 'erro');
                    }
                }
            );
        },

        // -------------------- USUÁRIOS (admin) --------------------
        async carregarUsuarios() {
            try {
                this.usuarios = await apiFetch('/admin/usuarios');
            } catch (e) {
                this.notificar('Não foi possível carregar os usuários.', 'erro');
            }
        },

        usuariosPendentesCount() {
            return this.usuarios.filter(u => u.status === 'pendente').length;
        },

        usuariosFiltrados() {
            if (this.usuariosFiltro === 'todos') return this.usuarios;
            return this.usuarios.filter(u => u.status === this.usuariosFiltro);
        },

        async aprovarUsuario(usuario) {
            try {
                await apiFetch(`/admin/usuarios/${usuario.id}/aprovar`, { method: 'POST' });
                await this.carregarUsuarios();
                this.notificar(`Usuário "${usuario.username}" aprovado.`, 'sucesso');
            } catch (e) {
                this.notificar(e.message, 'erro');
            }
        },

        reprovarUsuario(usuario) {
            this.pedirConfirmacao(
                'Reprovar usuário',
                `Tem certeza que deseja reprovar o acesso de "${usuario.username}"?`,
                async () => {
                    try {
                        await apiFetch(`/admin/usuarios/${usuario.id}/reprovar`, { method: 'POST' });
                        await this.carregarUsuarios();
                        this.notificar(`Usuário "${usuario.username}" reprovado.`, 'aviso');
                    } catch (e) {
                        this.notificar(e.message, 'erro');
                    }
                }
            );
        },

        iniciarEdicaoUsuario(usuario) {
            this.usuarioEditandoId = usuario.id;
            this.usuarioEdicaoForm = { username: usuario.username, password: '' };
        },

        async salvarEdicaoUsuario(usuario) {
            try {
                const payload = {};
                if (this.usuarioEdicaoForm.username && this.usuarioEdicaoForm.username !== usuario.username) {
                    payload.username = this.usuarioEdicaoForm.username;
                }
                if (this.usuarioEdicaoForm.password) {
                    payload.password = this.usuarioEdicaoForm.password;
                }
                await apiFetch(`/admin/usuarios/${usuario.id}`, {
                    method: 'PUT',
                    body: JSON.stringify(payload),
                });
                this.usuarioEditandoId = null;
                await this.carregarUsuarios();
                this.notificar('Usuário atualizado com sucesso.', 'sucesso');
            } catch (e) {
                this.notificar(e.message, 'erro');
            }
        },

        excluirUsuario(usuario) {
            this.pedirConfirmacao(
                'Excluir usuário',
                `Tem certeza que deseja excluir o cadastro de "${usuario.username}"? Essa ação é definitiva.`,
                async () => {
                    try {
                        await apiFetch(`/admin/usuarios/${usuario.id}`, { method: 'DELETE' });
                        await this.carregarUsuarios();
                        this.notificar(`Usuário "${usuario.username}" removido.`, 'aviso');
                    } catch (e) {
                        this.notificar(e.message, 'erro');
                    }
                }
            );
        },

        // -------------------- CHAT INTERNO --------------------
        linkify(texto) {
            // Escapa TUDO que poderia fechar uma tag/atributo HTML antes de
            // procurar por URLs — nessa ordem, importa escapar aspas
            // também: sem isso, uma mensagem como
            // `https://x.com" onmouseover="alert(1)` faria o "onmouseover"
            // vazar como um atributo de verdade na tag <a> gerada abaixo
            // (um XSS armazenado de verdade, não hipotético).
            const escapado = texto
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
            return escapado.replace(/(https?:\/\/[^\s<]+)/g, (url) => {
                return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="underline hover:opacity-80 break-all">${url}</a>`;
            });
        },

        async carregarChat(silencioso = false) {
            try {
                let query = '';
                if (this.chatGrupoAtual) query = `?grupo=${this.chatGrupoAtual.id}`;
                else if (this.chatConversaCom) query = `?com=${this.chatConversaCom.id}`;
                this.chatMensagens = await apiFetch(`/chat/mensagens${query}`);
                this.$nextTick(() => {
                    if (this.$refs.chatScroll) {
                        this.$refs.chatScroll.scrollTop = this.$refs.chatScroll.scrollHeight;
                    }
                });
            } catch (e) {
                if (!silencioso) this.notificar(`Não foi possível carregar o chat (${e.message}).`, 'erro');
            }
        },

        async enviarMensagemChat() {
            const conteudo = this.novaMensagemChat.trim();
            if (!conteudo || this.enviandoMensagemChat) return;
            this.enviandoMensagemChat = true;
            try {
                await apiFetch('/chat/mensagens', {
                    method: 'POST',
                    body: JSON.stringify({
                        conteudo,
                        destinatarioId: this.chatGrupoAtual ? null : (this.chatConversaCom ? this.chatConversaCom.id : null),
                        grupoId: this.chatGrupoAtual ? this.chatGrupoAtual.id : null,
                    }),
                });
                this.novaMensagemChat = '';
                await this.carregarChat();
            } catch (e) {
                this.notificar(e.message, 'erro');
            } finally {
                this.enviandoMensagemChat = false;
            }
        },

        iniciarEdicaoMensagem(msg) {
            this.mensagemEditandoId = msg.id;
            this.mensagemEditandoTexto = msg.conteudo;
        },
        cancelarEdicaoMensagem() {
            this.mensagemEditandoId = null;
            this.mensagemEditandoTexto = '';
        },
        async salvarEdicaoMensagem() {
            const conteudo = this.mensagemEditandoTexto.trim();
            if (!conteudo) return;
            try {
                await apiFetch(`/chat/mensagens/${this.mensagemEditandoId}`, {
                    method: 'PUT',
                    body: JSON.stringify({ conteudo }),
                });
                this.cancelarEdicaoMensagem();
                await this.carregarChat();
            } catch (e) {
                if (e.httpStatus === 404) {
                    this.cancelarEdicaoMensagem();
                    await this.carregarChat();
                    this.notificar('Esta mensagem já não existe mais.', 'aviso');
                    return;
                }
                this.notificar(e.message, 'erro');
            }
        },
        apagarMensagem(msg) {
            this.pedirConfirmacao(
                'Apagar mensagem',
                'Tem certeza que deseja apagar esta mensagem do chat?',
                async () => {
                    try {
                        await apiFetch(`/chat/mensagens/${msg.id}`, { method: 'DELETE' });
                        await this.carregarChat();
                    } catch (e) {
                        this.notificar(e.message, 'erro');
                    }
                }
            );
        },

        // -------------------- PERFIL RÁPIDO NO CHAT (clique no usuário) --------------------
        async abrirPerfilRapido(autorId, autorNome, autorFotoUrl, autorEhAdmin) {
            if (!autorId || autorId === this.usuarioAtual.id) return; // não abre popover para si mesmo
            this.perfilRapido = { id: autorId, nome: autorNome, fotoUrl: autorFotoUrl, ehAdmin: autorEhAdmin };
        },
        fecharPerfilRapido() {
            this.perfilRapido = null;
        },
        async iniciarConversaPrivada(usuario) {
            this.chatConversaCom = usuario;
            this.perfilRapido = null;
            this.mensagemEditandoId = null;
            await this.carregarChat();
        },
        async voltarParaChatGeral() {
            this.chatConversaCom = null;
            this.chatGrupoAtual = null;
            this.mensagemEditandoId = null;
            await this.carregarChat();
        },
        async carregarUsuariosChat() {
            try {
                this.chatUsuarios = await apiFetch('/chat/usuarios');
            } catch (e) { /* lista de conversas privadas fica vazia silenciosamente */ }
        },

        // -------------------- GRUPOS DE CHAT (canais) --------------------
        async carregarGrupos() {
            try {
                this.chatGrupos = await apiFetch('/chat/grupos');
            } catch (e) { /* lista de grupos fica vazia silenciosamente */ }
        },
        async entrarNoGrupo(grupo) {
            this.chatConversaCom = null;
            this.chatGrupoAtual = grupo;
            this.mensagemEditandoId = null;
            this.mostrarListaUsuariosChat = false;
            await this.carregarChat();
        },
        abrirModalNovoGrupo() {
            this.editandoGrupoId = null;
            this.novoGrupoForm = { nome: '', descricao: '', icone: 'fa-users', cor: 'indigo', membrosIds: [] };
            this.formErrorNovoGrupo = '';
            this.mostrarListaUsuariosChat = false;
            this.carregarUsuariosChat();
            this.modalNovoGrupoAberto = true;
        },
        abrirModalEditarGrupo(grupo) {
            this.editandoGrupoId = grupo.id;
            this.novoGrupoForm = { nome: grupo.nome, descricao: grupo.descricao, icone: grupo.icone, cor: grupo.cor, membrosIds: [] };
            this.formErrorNovoGrupo = '';
            this.modalNovoGrupoAberto = true;
        },
        fecharModalNovoGrupo() {
            this.modalNovoGrupoAberto = false;
        },
        async salvarGrupo() {
            if (this.enviandoNovoGrupo) return;
            this.formErrorNovoGrupo = '';
            this.enviandoNovoGrupo = true;
            try {
                if (this.editandoGrupoId) {
                    await apiFetch(`/chat/grupos/${this.editandoGrupoId}`, {
                        method: 'PUT',
                        body: JSON.stringify(this.novoGrupoForm),
                    });
                    this.notificar('Grupo atualizado.', 'sucesso');
                } else {
                    const grupo = await apiFetch('/chat/grupos', {
                        method: 'POST',
                        body: JSON.stringify(this.novoGrupoForm),
                    });
                    this.notificar(`Grupo "${grupo.nome}" criado.`, 'sucesso');
                    await this.entrarNoGrupo(grupo);
                }
                this.fecharModalNovoGrupo();
                await this.carregarGrupos();
            } catch (e) {
                this.formErrorNovoGrupo = e.message;
            } finally {
                this.enviandoNovoGrupo = false;
            }
        },
        sairDoGrupo(grupo) {
            this.pedirConfirmacao(
                'Sair do grupo',
                `Tem certeza que deseja sair do grupo "${grupo.nome}"? Você pode ser adicionado de volta por quem administra o grupo.`,
                async () => {
                    try {
                        await apiFetch(`/chat/grupos/${grupo.id}/membros/${this.usuarioAtual.id}`, { method: 'DELETE' });
                        if (this.chatGrupoAtual && this.chatGrupoAtual.id === grupo.id) {
                            await this.voltarParaChatGeral();
                        }
                        await this.carregarGrupos();
                        this.notificar(`Você saiu do grupo "${grupo.nome}".`, 'aviso');
                    } catch (e) {
                        this.notificar(e.message, 'erro');
                    }
                }
            );
        },
        excluirGrupo(grupo) {
            this.pedirConfirmacao(
                'Excluir grupo',
                `Isso apaga o grupo "${grupo.nome}" e todo o histórico de mensagens dele, para todos os membros. Esta ação não pode ser desfeita.`,
                async () => {
                    try {
                        await apiFetch(`/chat/grupos/${grupo.id}`, { method: 'DELETE' });
                        if (this.chatGrupoAtual && this.chatGrupoAtual.id === grupo.id) {
                            await this.voltarParaChatGeral();
                        }
                        await this.carregarGrupos();
                        this.notificar(`Grupo "${grupo.nome}" excluído.`, 'aviso');
                    } catch (e) {
                        this.notificar(e.message, 'erro');
                    }
                }
            );
        },
        async abrirGerenciarMembros(grupo) {
            this.grupoParaGerenciar = grupo;
            this.modalMembrosGrupoAberto = true;
            await this.carregarUsuariosChat();
            try {
                this.grupoMembrosAtual = await apiFetch(`/chat/grupos/${grupo.id}/membros`);
            } catch (e) {
                this.notificar(e.message, 'erro');
            }
        },
        fecharGerenciarMembros() {
            this.modalMembrosGrupoAberto = false;
            this.grupoParaGerenciar = null;
        },
        ehMembroDoGrupo(userId) {
            return this.grupoMembrosAtual.some(m => m.id === userId);
        },
        async alternarMembroGrupo(usuario) {
            try {
                if (this.ehMembroDoGrupo(usuario.id)) {
                    await apiFetch(`/chat/grupos/${this.grupoParaGerenciar.id}/membros/${usuario.id}`, { method: 'DELETE' });
                } else {
                    await apiFetch(`/chat/grupos/${this.grupoParaGerenciar.id}/membros`, {
                        method: 'POST',
                        body: JSON.stringify({ membrosIds: [usuario.id] }),
                    });
                }
                this.grupoMembrosAtual = await apiFetch(`/chat/grupos/${this.grupoParaGerenciar.id}/membros`);
                await this.carregarGrupos();
            } catch (e) {
                this.notificar(e.message, 'erro');
            }
        },
        corBadgeGrupo(cor) {
            const mapa = {
                indigo: 'bg-indigo-500/15 text-indigo-400', blue: 'bg-blue-500/15 text-blue-400',
                emerald: 'bg-emerald-500/15 text-emerald-400', amber: 'bg-amber-500/15 text-amber-400',
                rose: 'bg-rose-500/15 text-rose-400', violet: 'bg-violet-500/15 text-violet-400',
                cyan: 'bg-cyan-500/15 text-cyan-400', slate: 'bg-slate-500/15 text-slate-400',
            };
            return mapa[cor] || mapa.indigo;
        },

        // -------------------- BOTÃO FLUTUANTE DE CHAT --------------------
        async alternarChatFlutuante() {
            this.chatFlutuanteAberto = !this.chatFlutuanteAberto;
            if (this.chatFlutuanteAberto) {
                this.chatNaoLidas = 0;
                await this.carregarGrupos();
                await this.carregarChat();
            }
        },

        atualizarDataHora() {
            const now = new Date();
            this.dataHora = now.toLocaleString('pt-BR', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        },

        // -------------------- TEMA (claro/escuro) --------------------
        // A troca de tema funciona por um atributo `data-tema` na tag
        // <html>; as regras que "reskinam" as classes Tailwind escuras
        // para uma paleta clara estão em app.css (seção TEMA CLARO).
        aplicarTema(tema) {
            const t = tema === 'claro' ? 'claro' : 'escuro';
            document.documentElement.setAttribute('data-tema', t);
            if (!this.loggedIn) localStorage.setItem('sca_tema_visitante', t);
            if (this.usuarioAtual) this.usuarioAtual.tema = t;
        },
        async alternarTema() {
            const novo = (this.usuarioAtual.tema === 'claro') ? 'escuro' : 'claro';
            this.aplicarTema(novo);
            if (!this.loggedIn) return; // visitante: só localStorage mesmo
            try {
                await apiFetch('/auth/tema', { method: 'PUT', body: JSON.stringify({ tema: novo }) });
            } catch (e) {
                this.notificar('Não foi possível salvar sua preferência de tema.', 'erro');
            }
        },

        // -------------------- PERFIL DO PRÓPRIO USUÁRIO --------------------
        abrirModalPerfil() {
            this.perfilForm = { nome: this.usuarioAtual.nome || '' };
            this.senhaForm = { senhaAtual: '', novaSenha: '', confirmarSenha: '' };
            this.formErrorPerfil = '';
            this.formErrorSenha = '';
            this.perfilTab = 'dados';
            this.modalPerfilAberto = true;
            this.carregarSessoes();
        },
        fecharModalPerfil() {
            this.modalPerfilAberto = false;
        },
        async salvarPerfil() {
            if (this.salvandoPerfil) return;
            this.formErrorPerfil = '';
            this.salvandoPerfil = true;
            try {
                const atualizado = await apiFetch('/auth/perfil', {
                    method: 'PUT',
                    body: JSON.stringify({ nome: this.perfilForm.nome }),
                });
                this.usuarioAtual = { ...this.usuarioAtual, ...atualizado };
                this.notificar('Perfil atualizado com sucesso.', 'sucesso');
            } catch (e) {
                this.formErrorPerfil = e.message;
            } finally {
                this.salvandoPerfil = false;
            }
        },
        async salvarSenha() {
            if (this.salvandoPerfil) return;
            this.formErrorSenha = '';
            if (this.senhaForm.novaSenha !== this.senhaForm.confirmarSenha) {
                this.formErrorSenha = 'A confirmação não corresponde à nova senha.';
                return;
            }
            this.salvandoPerfil = true;
            try {
                await apiFetch('/auth/perfil', {
                    method: 'PUT',
                    body: JSON.stringify({
                        nome: this.perfilForm.nome,
                        senhaAtual: this.senhaForm.senhaAtual,
                        novaSenha: this.senhaForm.novaSenha,
                    }),
                });
                this.senhaForm = { senhaAtual: '', novaSenha: '', confirmarSenha: '' };
                this.notificar('Senha alterada com sucesso.', 'sucesso');
            } catch (e) {
                this.formErrorSenha = e.message;
            } finally {
                this.salvandoPerfil = false;
            }
        },
        async enviarFotoPerfil(evento) {
            const arquivo = evento.target.files[0];
            if (!arquivo) return;
            this.enviandoFotoPerfil = true;
            try {
                const formData = new FormData();
                formData.append('arquivo', arquivo);
                const atualizado = await apiUpload('/auth/perfil/foto', formData);
                this.usuarioAtual = { ...this.usuarioAtual, ...atualizado };
                this.notificar('Foto de perfil atualizada.', 'sucesso');
            } catch (e) {
                this.notificar(e.message, 'erro');
            } finally {
                this.enviandoFotoPerfil = false;
                evento.target.value = '';
            }
        },
        iniciaisUsuario(usuario) {
            const nome = (usuario && (usuario.nome || usuario.username)) || '?';
            return nome.trim().slice(0, 2).toUpperCase();
        },

        // -------------------- SESSÕES ATIVAS (multi-dispositivo) --------------------
        async carregarSessoes() {
            this.carregandoSessoes = true;
            try {
                const resp = await apiFetch('/auth/sessoes');
                this.sessoesAtivas = resp.sessoes;
            } catch (e) {
                this.notificar('Não foi possível carregar suas sessões ativas.', 'erro');
            } finally {
                this.carregandoSessoes = false;
            }
        },
        async encerrarSessao(sessao) {
            try {
                await apiFetch(`/auth/sessoes/${sessao.id}`, { method: 'DELETE' });
                if (sessao.atual) {
                    // Encerrou a própria sessão atual: o cookie local já caiu
                    // no servidor, então reflete isso aqui também.
                    this.notificar('Você saiu deste dispositivo.', 'aviso');
                    await this.logout();
                    return;
                }
                await this.carregarSessoes();
                this.notificar('Sessão encerrada.', 'sucesso');
            } catch (e) {
                this.notificar(e.message, 'erro');
            }
        },
        encerrarOutrasSessoes() {
            this.pedirConfirmacao(
                'Encerrar outras sessões',
                'Isso vai desconectar todos os outros dispositivos/navegadores onde sua conta está logada, exceto este. Continuar?',
                async () => {
                    try {
                        await apiFetch('/auth/sessoes/encerrar-outras', { method: 'POST' });
                        await this.carregarSessoes();
                        this.notificar('As demais sessões foram encerradas.', 'sucesso');
                    } catch (e) {
                        this.notificar(e.message, 'erro');
                    }
                }
            );
        },

        // -------------------- NOTIFICAÇÕES DO NAVEGADOR --------------------
        pedirPermissaoNotificacao() {
            if (!('Notification' in window)) return;
            if (Notification.permission === 'default') {
                Notification.requestPermission().then((perm) => {
                    this.notificacoesPermitidas = perm === 'granted';
                });
            } else {
                this.notificacoesPermitidas = Notification.permission === 'granted';
            }
        },
        notificarNavegador(titulo, corpo) {
            if (!('Notification' in window) || Notification.permission !== 'granted') return;
            // Só notifica quando a aba não está em foco — evita duplicar
            // aviso com o toast interno enquanto a pessoa já está olhando.
            if (document.visibilityState === 'visible') return;
            try {
                new Notification(titulo, { body: corpo, icon: '/static/uploads/favicon.png' });
            } catch (e) { /* navegadores que bloqueiam silenciosamente */ }
        },

        // -------------------- SINCRONIZAÇÃO QUASE EM TEMPO REAL --------------------
        // Ver app/api/sync.py para a explicação da escolha por polling.
        async atualizarMarcadoresSync() {
            try {
                this.ultimaSync = await apiFetch('/sync');
            } catch (e) { /* tenta de novo no próximo ciclo */ }
        },
        async verificarSincronizacao() {
            if (!this.podeVerAreaPublica()) return;
            try {
                const atual = await apiFetch('/sync');
                if (atual.avisos !== this.ultimaSync.avisos) {
                    await this.carregarAvisos();
                    this.notificar('Os avisos foram atualizados.', 'aviso');
                    this.notificarNavegador('Novo aviso publicado', 'Há uma atualização nos avisos do sistema.');
                }
                if (atual.cidades !== this.ultimaSync.cidades) {
                    await this.carregarCidades();
                    this.notificar('As cidades foram atualizadas.', 'aviso');
                }
                if (atual.chatUltimoId !== this.ultimaSync.chatUltimoId) {
                    const vendoChatEmAba = this.page === 'public' && this.publicTab === 'chat';
                    if (vendoChatEmAba || this.chatFlutuanteAberto) {
                        await this.carregarChat(true);
                    } else {
                        this.chatNaoLidas += 1;
                        this.notificar('Nova mensagem no chat interno.', 'aviso');
                        this.notificarNavegador('Nova mensagem no chat', 'Há uma nova mensagem no chat interno.');
                    }
                }
                if (this.usuarioAtual.role === 'admin' && atual.usuarios !== this.ultimaSync.usuarios && this.adminTab === 'usuarios') {
                    await this.carregarUsuarios();
                }
                this.ultimaSync = atual;
            } catch (e) { /* sem sessão válida ou rede instável: tenta de novo depois */ }
        },

        // -------------------- ÍCONES ANIMADOS DOS AVISOS --------------------
        iconeAviso(aviso) {
            const porTipo = {
                urgente: 'fa-triangle-exclamation',
                atencao: 'fa-circle-exclamation',
                informativo: 'fa-bullhorn',
            };
            return porTipo[aviso.tipo] || 'fa-bullhorn';
        },
        animacaoIconeAviso(aviso) {
            if (aviso.status === 'Expirado') return '';
            if (aviso.tipo === 'urgente') return 'anim-shake';
            if (aviso.tipo === 'atencao') return 'animate-pulse';
            return 'anim-bounce-soft';
        },
        corIconeAviso(aviso) {
            const porTipo = { urgente: 'text-rose-400 bg-rose-500/10', atencao: 'text-amber-400 bg-amber-500/10', informativo: 'text-indigo-400 bg-indigo-500/10' };
            return porTipo[aviso.tipo] || porTipo.informativo;
        },
        rotuloTipoAviso(tipo) {
            return { informativo: 'Informativo', atencao: 'Atenção', urgente: 'Urgente' }[tipo] || 'Informativo';
        },
        podeGerenciarAviso(aviso) {
            return this.usuarioAtual.role === 'admin' || aviso.autorId === this.usuarioAtual.id;
        },

        // -------------------- NOVO USUÁRIO (admin cria diretamente) --------------------
        abrirModalNovoUsuario() {
            this.novoUsuarioForm = { username: '', password: '', role: 'usuario' };
            this.formErrorNovoUsuario = '';
            this.modalNovoUsuarioAberto = true;
        },
        fecharModalNovoUsuario() {
            this.modalNovoUsuarioAberto = false;
        },
        async criarUsuario() {
            if (this.enviandoNovoUsuario) return;
            this.formErrorNovoUsuario = '';
            this.enviandoNovoUsuario = true;
            try {
                await apiFetch('/admin/usuarios', {
                    method: 'POST',
                    body: JSON.stringify(this.novoUsuarioForm),
                });
                this.fecharModalNovoUsuario();
                await this.carregarUsuarios();
                this.notificar(`Usuário "${this.novoUsuarioForm.username}" criado com sucesso.`, 'sucesso');
            } catch (e) {
                this.formErrorNovoUsuario = e.message;
            } finally {
                this.enviandoNovoUsuario = false;
            }
        },
        async alternarRoleUsuario(usuario) {
            const novaRole = usuario.role === 'admin' ? 'usuario' : 'admin';
            const acaoTexto = novaRole === 'admin' ? 'promover a administrador' : 'remover os privilégios de administrador de';
            this.pedirConfirmacao(
                novaRole === 'admin' ? 'Promover a administrador' : 'Remover privilégios de admin',
                `Tem certeza que deseja ${acaoTexto} "${usuario.username}"?`,
                async () => {
                    try {
                        await apiFetch(`/admin/usuarios/${usuario.id}`, {
                            method: 'PUT',
                            body: JSON.stringify({ role: novaRole }),
                        });
                        await this.carregarUsuarios();
                        this.notificar(`Papel de "${usuario.username}" atualizado.`, 'sucesso');
                    } catch (e) {
                        this.notificar(e.message, 'erro');
                    }
                }
            );
        },

    };
}
