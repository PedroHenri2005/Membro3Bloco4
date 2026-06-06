let blocosDeEstudo = []; // guarda o JSON com as frases 
let blocoAtualIndex = 0; // qual frase o usuário está no momento
currentVideoTitle = "Vídeo do Youtube"; // O título do vídeo do Youtube. Por padrão, deixarei ela inicialmente como essa string.
currentVideoId = ""; // O ID do vídeo.
startTime = 0; // O tempo de início da legenda.
endTime = 0; // O tempo de fim da legenda.
let deckSelecionadoId = null; // [ MEMBRO 3 - BLOCO 4 ]: Variável para guardar o ID do Deck que o usuário selecioanr no novo modal de escolha de Decks.
let modoSubModal = "criar"; // [ MEMBRO 3 - BLOCO 4 ]: Aqui, controlamos o modo do submodal que servirá para coletar nomes de Decks que vão ser criados/renomeados.
// Dependendo da origem do botão que requeriu o submodal, existem dois modos: "criar" ou "renomear".
window.emModoRevisao = false;

function mostrarCarregamento(mensagem) {
    const carregamento = document.getElementById("carregamento");
    const texto = document.getElementById("carregamentoTexto");
    if (texto && mensagem) texto.innerText = mensagem;
    if (carregamento) carregamento.style.display = "flex";
}

function esconderCarregamento() {
    const carregamento = document.getElementById("carregamento");
    if (carregamento) carregamento.style.display = "none";
}

async function iniciarSessao(youtubeLink) {
    try {
        const botaoIniciar = document.getElementById('protecaoButton');
        if (botaoIniciar) {
            botaoIniciar.style.background = "black";
            botaoIniciar.disabled = true;
        }

        // Aqui no início faz sentido ter a tela de carregamento!
        mostrarCarregamento("Extraindo legendas e preparando áudio...");

        const resposta = await fetch(`/api/legenda?url=${encodeURIComponent(youtubeLink)}`);
        const jsonResponse = await resposta.json();

        if (!resposta.ok) {
            if (jsonResponse.tokens_restantes !== undefined) {
                atualizarInterfaceTokens(jsonResponse.tokens_restantes);
            }
            throw new Error(jsonResponse.detail || "Erro ao carregar legenda.");
        }

        blocosDeEstudo = jsonResponse.dados;
        currentVideoTitle = jsonResponse.titulo_video;
        atualizarInterfaceTokens(jsonResponse.tokens_restantes);
        blocoAtualIndex = 0;
        currentVideoId = extractVideoId(youtubeLink);

        loadVideo(currentVideoId);

        // [ MEMBRO 3 - BLOCO 4 ]: Aqui, localizo os elementos do novo modal e injeto o log de aviso:
        const modalLegenda = document.getElementById("modalLegendaTitulo");
        const textoLogs = document.getElementById("textologs");

        if (modalLegenda && textoLogs && jsonResponse.aviso_legenda) {
            textoLogs.innerText = jsonResponse.aviso_legenda; // Defino a string que foi construída no main.py pela rota GET.
            modalLegenda.style.display = "flex"; // E então, fazemos o modal aparecer na tela.
        }

        let tentativas = 0;
        while (!document.getElementById("legenda") && tentativas < 50) {
            await new Promise(r => setTimeout(r, 100));
            tentativas++;
        }

        await carregarFraseAtual();

    } catch (erro) {
        const erroModal = document.getElementById("erroModal");
        const erroText = document.getElementById("erro");
        if (erroModal && erroText) {
            erroText.innerText = erro.message;
            erroModal.style.display = "block";
        }
        console.error("Falha na integração:", erro);
    } finally {
        esconderCarregamento();
    }
}

function atualizarInterfaceTokens(valor) {
    localStorage.setItem("tokens_restantes", valor);
    const el = document.getElementById("token-count");
    if (!el) return;
    el.innerText = valor;
    if (parseInt(valor) === 0) {
        el.classList.add("token-low");
    } else {
        el.classList.remove("token-low");
    }
}

async function carregarFraseAtual() {
    // [ MEMBRO 3 - BLOCO 4 ]: Garanto que o botão da tela principal volte ao estado normal "Salvar Card" sempre que mudamos de frase:
    const btnSalvarPrincipal = document.getElementById("salvar");
    if (btnSalvarPrincipal) {
        btnSalvarPrincipal.innerText = "Salvar Card";
    }
    
    if (!blocosDeEstudo || blocosDeEstudo.length === 0) return;

    const bloco = blocosDeEstudo[blocoAtualIndex];

    const renderizarQuandoExistir = () => {
        const legendaDiv = document.getElementById("legenda");
        if (legendaDiv && typeof renderizarLegenda === "function") {
            renderizarLegenda(bloco.texto_limpo);
            return true;
        } else if (legendaDiv) {
            legendaDiv.innerText = bloco.texto_limpo;
            return true;
        }
        return false;
    };

    if (!renderizarQuandoExistir()) {
        await new Promise((resolve) => {
            const observer = new MutationObserver(() => {
                if (renderizarQuandoExistir()) {
                    observer.disconnect();
                    resolve();
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
            setTimeout(() => { observer.disconnect(); resolve(); }, 5000);
        });
    }

    const panel = document.getElementById("panel");
    const transcript = document.getElementById("transcript");

    if (panel) panel.classList.remove("hidden");

    startTime = bloco.tempo_inicio;
    endTime = bloco.tempo_fim;

    const tempoTotal = endTime - startTime;
    const link = new URLSearchParams(window.location.search).get("link");
    const audioURL = `/api/audio?url=${encodeURIComponent(link)}&inicio=${startTime}&fim=${endTime}`;

    if (transcript) {
        //transcript.style.display = "none"; tirei pra atualizar sem piscar
        transcript.innerText = "Fale algo...";
    }

    if (typeof resetarTimerVisual === "function") resetarTimerVisual();

    try {
        if (typeof carregarWaveform === "function") {
            await carregarWaveform(audioURL, tempoTotal);
        }

        if (typeof aguardarPlayerPronto === "function") {
            await aguardarPlayerPronto();
        }

        
        if (player && typeof player.seekTo === "function") {
            player.seekTo(startTime, true);
            player.playVideo();
            if (typeof startLoop === "function") startLoop();
        }

        // Continua fazendo o download silencioso das próximas 2 frases
        for (let i = blocoAtualIndex + 1; i <= blocoAtualIndex + 2; i++) {
            if (i >= blocosDeEstudo.length) continue;
            const prox = blocosDeEstudo[i];
            const proxURL = `/api/audio?url=${encodeURIComponent(link)}&inicio=${prox.tempo_inicio}&fim=${prox.tempo_fim}`;
            fetch(proxURL).catch(console.error);
        }
    } catch(e) {
        console.error(e);
    }
}

document.addEventListener("click", function(event) {
    // [ MEMBRO 3 - BLOCO 4 ]: Aqui está a lógica de escuta do clique no botão "Continuar" do novo modal, que informa sobre tipo de legenda e título do vídeo:
    if (event.target.id === "botaoContinuar") {
        const modalLegenda = document.getElementById("modalLegendaTitulo");
        if (modalLegenda) {
            modalLegenda.style.display = "none"; // Quando o usuário clicar em "Continuar", o modal deve sumir.
        }
    }

    if (event.target.id === "protecaoButton") {
        const overlay = document.getElementById("protecaoPlayer");
        if (overlay) overlay.style.display = "none";
        
        // [ MEMBRO 3 - BLOCO 4 ]: Agora, de fato o vídeo só começa a tocar depois que o usuário clica em "Iniciar Estudos":
        if (player && typeof player.playVideo === "function") {
            player.playVideo();
            if (typeof startLoop === "function") {
                startLoop();
            }
        }
    }
    // [ MEMBRO 3 - BLOCO 4 ]: Além disso, é necessário fazer com que o botão "Salvar Card" da página 2 redirecione para o novo modal de escolha de Decks:
    if (event.target.id === "salvar") {
        const btnSalvarPrincipal = event.target;

        // Se o botão já estava como "Salvo!", o primeiro clique apenas reseta o texto:
        if (btnSalvarPrincipal.innerText === "Salvo!") {
            btnSalvarPrincipal.innerText = "Salvar Card";
            return; // Interrompe aqui. O modal NÃO abre neste clique, apenas o texto foi resetado para "Salvar Card" novamente. 
            // Se depois disso, o usuário clicar em "Salvar Card", vai ter o mesmo funcionamento de sempre.
        }
    
        // Mas se o botão estava como "Salvar Card", o botão segue o comportamento padrão de abrir o modal:
        const modalDeck = document.getElementById("modalDeck");
        if (modalDeck) {
            modalDeck.style.display = "flex"; // Fazemos o modal aparecer na tela.
            // Toda vez que esse modal abrir, precisamos carregar os Decks presentes no BD, para o usuário ser capaz de ver eles:
            carregarDecks(); // A lógica da função usada aqui está logo abaixo dessa função escutadora de cliques.
        }
    }
    // [ MEMBRO 3 - BLOCO 4 ]: Também é necessário escutar o clique no botão "Salvar Card" do rodapé do modal principal:
    if (event.target.id === "btnSalvar") {
        // Buscamos o bloco de estudo atual, com base no índice da tela:
        const bloco = blocosDeEstudo[blocoAtualIndex];
        if (!bloco) return;
        // Chamamos a função auxiliar organizada, passando todas as variáveis globais necessárias
        executarSalvamentoDeCard(deckSelecionadoId, currentVideoId, bloco.texto_limpo, startTime, endTime);
    }
    // [ MEMBRO 3 - BLOCO 4 ]: Também vai ser necessário fazer a lógica do submodal, que abre quando o usuário clica em "Criar Deck".
    // Além disso, quando o usuário estiver na página3.html, o mesmo submodal será utilizado para obter o nome do novo Deck criado:
    // Para cobrir cada um dos casos das linhas anteriores, temos o OU desse próximo if:
    if (event.target.id === "btnCriarDeckModal" || event.target.id === "btnCriarDeckRevisao") {
        const subModal = document.getElementById("subModalCriarDeck");
        const inputNome = document.getElementById("novoNomeDeckInput");
        
        if (subModal) {
            subModal.style.display = "flex"; // Faço o submodal aparecer.
            
            // Limpo o campo e coloco o cursor do teclado nele:
            if (inputNome) {
                inputNome.value = "";
                inputNome.focus();
            }
        }
    }
    // [ MEMBRO 3 - BLOCO 4 ]: Após isso, quando o usuário decidir o nome do novo Deck e clicar no botão "OK" para salvar o Deck no BD, a seguinte lógica será executada:
    if (event.target.id === "btnConfirmarCriarDeck") {
        const inputNome = document.getElementById("novoNomeDeckInput");
        // Pegamos o valor digitado e usamos o .trim() para ignorar espaços inúteis digitados antes ou depois do texto:
        let nomeDigitado = inputNome ? inputNome.value.trim() : "";

        // Se o usuário tentar criar um Deck de nome vazio, automaticamente o nome desse Deck será "Deck":
        if (nomeDigitado === "") {
        nomeDigitado = "Deck";
        }

        // Depois, usamos o modo do submodal para decidir se o usuário está criando ou renomeando um Deck:
        if (modoSubModal === "criar") {
            executarCriacaoDeDeck(nomeDigitado); // Se passar da validação, chamamos a função auxiliar que faz o envio para o main.py, para formatarmos os dados e sermos capazes de usar a ROTA 2.
            // Essa função se encontra um pouco abaixo dessa função escutadora de cliques, logo abaixo da função carregarDecks().
        }
        else if (modoSubModal === "renomear") {
            executarRenomeacaoDeDeck(deckSelecionadoId, nomeDigitado); // Essa função auxiliar usará a ROTA 5 do main.py, própria para renomear Decks. 
            // O código dela está abaixo dessa função escutadora de cliques também.
        }
    }
    // [ MEMBRO 3 - BLOCO 4 ]: Analogamente, uma lógica inversa para os botões que servem para fechar o submodal:
    if (event.target.id === "btnCancelarSubModalX" || event.target.id === "btnCancelarSubModal") {
        const subModal = document.getElementById("subModalCriarDeck");
        if (subModal) {
            subModal.style.display = "none"; // Oculta o submodal e mantém o modal de trás aberto
        }
    }
    // [ MEMBRO 3 - BLOCO 4 ]: A lógica inversa ao bloco de if do botão "Salvar Card" que abre o modal principal também vale para os botões "X" e "Cancelar" desse modal, para fechá-lo:
    if (event.target.id === "btnCancelar" || event.target.id === "btnCancelarRodape") {
        const modalDeck = document.getElementById("modalDeck");
        if (modalDeck) {
            modalDeck.style.display = "none";
        }
    }
    // [ MEMBRO 3 - BLOCO 4 ]: Escuta o clique no botão "Deletar Deck" do rodapé do modal principal
    if (event.target.id === "btnDeletarDeckModal") {
        // Confirmação de segurança:
        const confirmar = confirm("Tem certeza absoluta de que deseja deletar o baralho selecionado?");
        if (!confirmar) {
            return; // Se o usuário clicar em cancelar, interrompe e não deleta
        }

        // Se confirmou e tem ID válido, chamo a função auxiliar assíncrona para deletar:
        executarDelecaoDeDeck(deckSelecionadoId);
    }

    if (event.target.id === "botaoErro") {
        const modal = document.getElementById("erroModal");
        if (modal) modal.style.display = "none";
    }

    if (event.target.id === "proximo") {
        if (blocoAtualIndex < blocosDeEstudo.length - 1) {
            blocoAtualIndex++;
            void carregarFraseAtual();
        }
    }

    if (event.target.id === "anterior") {
        if (blocoAtualIndex > 0) {
            blocoAtualIndex--;
            void carregarFraseAtual();
        }
    }
});

// --- [ MEMBRO 3  - BLOCO 4 ]: FUNÇÕES AUXILIARES PARA A MANUTENÇÂO DOS DECKS E CARDS NO BD ---

// [ MEMBRO 3 - BLOCO 4 ] - Função carregarDecks(), para controlar e renderizar Decks no novo modal:
async function carregarDecks() {

    const listaUl = document.getElementById("listaDecks"); // Começo obtendo o pedaço do HTML que corresponde a lista de Decks, no novo modal.
    const btnDeletar = document.getElementById("btnDeletarDeckModal"); // Capturo o botão "Deletar Deck", para ele ficar bloquado enquanto nenhum Deck é selecionado.
    const btnSalvar = document.getElementById("btnSalvar"); // Faço o mesmo para o botão "Salvar Card".

    if (!listaUl) return; 

    try {
        // E então, uso a ROTA 1 criada no main.py para listar os Decks do BD:
        const resposta = await fetch("/api/listar_decks");
        if (!resposta.ok) throw new Error("Erro ao buscar baralhos.");
        
        const decks = await resposta.json(); // Depois, transformamos o JSON em um array do JS.
        
        // E então, limpo a lista antiga para não duplicar visualmente os itens na tela:
        listaUl.innerHTML = "";
        deckSelecionadoId = null; // Precisamos resetar o Deck selecionado toda vez que a lista carrega também.

        // E então, reseto o campo de texto do filtro, para ele começar completamente vazio toda vez que o modal abre:
        const inputBusca = document.getElementById("filtroInput");
        if (inputBusca) {
            inputBusca.value = ""; 

            // Removemos qualquer escutador antigo (para evitar duplicidade), e adicionamos o novo:
            inputBusca.removeEventListener("input", filtrarDecks);
            inputBusca.addEventListener("input", filtrarDecks);
        }

        // Sempre que a lista é recarregada, o botão começa DESABILITADO:
        if (btnDeletar) btnDeletar.disabled = true;
        if (btnSalvar) btnSalvar.disabled = true;

        // Se o BD estiver novo (ou sem nenhum Deck), podemos retornar um aviso para o usuário:
        if (decks.length === 0) {
            // [ MEMBRO 1 && MEMBRO 3 - BLOCO 4, PARTE 4/5 ]: Essa mensagem pode ter seu estilo alterado.
            listaUl.innerHTML = `<li class="modal-deck-item apenas-texto" style="color: #888; cursor: default; text-align: center; padding: 15px;">Nenhum Deck encontrado.</li>`;
            return;
        }

        // Se houver decks, vamos criar um <li> para cada um deles:
        decks.forEach(deck => {
            const li = document.createElement("li");
            li.className = "modal-deck-item";
            li.innerText = deck.nome;
            li.dataset.id = deck.id; // Guardo o ID do banco escondido dentro da tag HTML

            // Adiciono também um escutador de cliques individual para seleção visual (fundo azul):
            li.addEventListener("click", function() {
                // Começo removendo a classe "selected" de todos os itens (Decks) da lista:
                document.querySelectorAll(".modal-deck-item").forEach(item => {
                    item.classList.remove("selected");
                });

                // E então adiciono a classe "selected" (azul) apenas neste que foi clicado:
                li.classList.add("selected");
                
                // Além disso, salvo o ID deste deck na nossa variável de controle global:
                deckSelecionadoId = deck.id;
                console.log("Deck selecionado atualmente:", deck.nome, "(ID:", deckSelecionadoId + ")");

                // Quando o usuário clica em um deck válido, o botão "Deletar Deck" é desbloqueado:
                if (btnDeletar) btnDeletar.disabled = false;
                if (btnSalvar) btnSalvar.disabled = false;
            });

            // E adiciono o elemento <li> recém-criado dentro da nossa <ul>:
            listaUl.appendChild(li);
        });

    } catch (erro) {
        console.error("Erro ao renderizar decks:", erro);
        // [ MEMBRO 1 && MEMBRO 3 - BLOCO 4, PARTE 5/5 ]: Essa mensagem pode ter seu estilo alterado.
        listaUl.innerHTML = `<li class="modal-deck-item" style="color: #ff6b6b; cursor: default; padding: 15px;">Erro ao carregar baralhos.</li>`;
    }
}

// [ MEMBRO 3 - BLOCO 4 ] - Função que filtra os Decks visualmente, com base na digitação do usuário:
function filtrarDecks() {
    const inputBusca = document.getElementById("filtroInput"); 
    const listaUl = document.getElementById("listaDecks");
    if (!inputBusca || !listaUl) return;

    // Convertemos o termo digitado para letras minúsculas, e removemos espaços nas pontas.
    // Isso garante que buscar "culinária", "Culinaria" ou "CULINÁRIA" funcione igual:
    const termoBusca = inputBusca.value.toLowerCase().trim();

    // Capturamos todos os itens <li> que estão dentro da nossa lista <ul>:
    const itens = listaUl.querySelectorAll(".modal-deck-item");

    // Varremos item por item para aplicar o filtro
    itens.forEach(item => {
        // Se for a mensagem de "Nenhum baralho encontrado", ignoramos o filtro nela:
        if (item.classList.contains("apenas-texto")) return;

        const nomeDoBaralho = item.innerText.toLowerCase();

        // Checagem se o nome do baralho contém o termo que o usuário digitou:
        if (nomeDoBaralho.includes(termoBusca)) {
            item.style.display = ""; // Se sim, fazemos o nome do Deck aparecer.
        } else {
            item.style.display = "none"; // Se não, o nome do Deck não deve aparecer.
        }
    });
}

// [ MEMBRO 3 - BLOCO 4 ] - Função auxiliar responsável por enviar os dados via POST para salvar o Card no BD:
async function executarSalvamentoDeCard(idDoDeck, idDoVideo, textoLegenda, tempoInicio, tempoFim) {
    try {
        // Preparo os dados, simulando o envio de um formulário tradicional padrão do FastAPI (Form(...)):
        const dadosCard = new FormData();
        dadosCard.append('deck_id', idDoDeck);
        dadosCard.append('video_id', idDoVideo);
        dadosCard.append('texto_legenda', textoLegenda);
        dadosCard.append('start_time', tempoInicio);
        dadosCard.append('end_time', tempoFim);

        // Faço o disparo assíncrono para a ROTA 4 do main.py:
        const resposta = await fetch('/salvar_card', {
            method: 'POST',
            body: dadosCard
        });

        const data = await resposta.json();

        if (resposta.ok) {
            
            // CASO 1: O main.py detectou que o Card é DUPLICADO naquele Deck
            if (data.status === 'duplicado') {
                // Então, exibo o alerta avisando que o Card já foi salvo anteriormente nesse Deck:
                alert(`⚠️ ${data.mensagem}`);
                
                // E assim fecho o modal:
                const modalDeck = document.getElementById('modalDeck');
                if (modalDeck) modalDeck.style.display = "none";
                
                deckSelecionadoId = null;
                return; // Interrompo a execução aqui (não altero o botão da tela principal para "Salvo!").
            }

            // CASO 2: Sucesso (Card inédito salvo)
            if (data.status === 'sucesso') {
                // Capturo o botão da tela principal e mudo o texto:
                const btnSalvarTelaPrincipal = document.getElementById("salvar");
                if (btnSalvarTelaPrincipal) {
                    btnSalvarTelaPrincipal.innerText = "Salvo!";
                }
                
                // E assim fecho o modal:
                const modalDeck = document.getElementById('modalDeck');
                if (modalDeck) modalDeck.style.display = "none";
                
                deckSelecionadoId = null;
            }

        } else {
            // Caso ocorra algum erro crítico de validação ou banco de dados (ex: status 404 ou 500):
            alert("Erro ao salvar: " + (data.mensagem || data.detail || "Erro desconhecido"));
        }

    } catch (erro) {
        console.error("Erro na requisição de salvamento:", erro);
        alert("Falha técnica ao tentar salvar o cartão.");
    }
}

// [ MEMBRO 3 - BLOCO 4 ] - Função responsável por enviar dados via POST para criação de um Deck:
async function executarCriacaoDeDeck(nome) {
    try {
        // Criamos o objeto FormData, porque a rota Python espera um parâmetro do tipo Form(...):
        const dadosFormulario = new FormData();
        dadosFormulario.append("nome", nome); // Adiciona a chave "nome", com o valor recebido por parâmetro.

        // Finalmente disparamos a requisição assíncrona para a ROTA 2:
        const resposta = await fetch("/api/criar_deck", {
            method: "POST",
            body: dadosFormulario
        });

        // E então, transformamos o 'content' JSON enviado pelo main.py em um objeto JavaScript manipulável:
        const resultado = await resposta.json();

        // Caso de erro (status_code=400): Se caiu na checagem de "deck_duplicado" do Python:
        if (!resposta.ok) {
            // Exibo um alert com a mensagem enviada pelo back-end: "Já existe um baralho com este nome."
            alert(`Erro: ${resultado.mensagem}`);
            return; // Para a execução da função aqui. O submodal continua aberto para o usuário corrigir.
        }

        // Por outro lado, caso o usuário tenha sucesso em criar o Deck, escondo o submodal automaticamente, já que o baralho foi salvo:
        const subModal = document.getElementById("subModalCriarDeck");
        if (subModal) {
            subModal.style.display = "none";
        }

        // Aqui, obtennho a variável que representa o Dashboard da pagina3.html:
        const tabelaDashboard = document.getElementById("corpoTabelaDecksRevisao");

        // Se estivermos na nova pagina3.html (Dashboard de Decks), a lógica é diferente:
        if (tabelaDashboard) {
            // Se essa tabela existe na tela, o usuário está na pagina3.html.
            // Então, chamo a função do Dashboard para atualizar a tabela na hora.
            await carregarDashboardDecks(); 
        } else {
            // Se não existe, então ele está na pagina2.html.
            // Chamo então a função antiga para atualizar a lista do modal de escolha.
            await carregarDecks(); 
        }

    } catch (erro) {
        console.error("Erro na comunicação com o servidor ao criar deck:", erro);
        alert("Ocorreu um erro inesperado ao tentar se comunicar com o servidor.");
    }
}

// [ MEMBRO 3 - BLOCO 4 ] - Função responsável por renomear Decks:
async function executarRenomeacaoDeDeck(id, novoNome) {
    try {
        const dadosFormulario = new FormData();
        dadosFormulario.append("deck_id", id);
        dadosFormulario.append("nome", novoNome);

        const resposta = await fetch("/api/renomear_deck", {
            method: "POST",
            body: dadosFormulario
        });

        if (resposta.ok) {
            const subModal = document.getElementById("subModalCriarDeck");
            if (subModal) subModal.style.display = "none";
            
            await carregarDashboardDecks(); // Atualiza a tabela na hora
        } else {
            alert("Erro ao tentar renomear o deck.");
        }
    } catch (erro) {
        console.error("Erro ao renomear deck:", erro);
    }
}

// [ MEMBRO 3 - BLOCO 4 ] - Função responsável por fazer o POST para deletar Decks:
async function executarDelecaoDeDeck(idDoDeck) {
    try {
        // Começo preparando os dados simulando um formulário que o 'Form(...)' que a ROTA 3 do main.py exige:
        const dadosFormulario = new FormData();
        dadosFormulario.append("deck_id", idDoDeck);

        // E então, faço a requisição enviando o pacote:
        const resposta = await fetch("/api/deletar_deck", {
            method: "POST",
            body: dadosFormulario
        });

        const resultado = await resposta.json();

        // Se o servidor retornar erro:
        if (!resposta.ok) {
            alert(`Erro: ${resultado.mensagem}`);
            return;
        }

        // Muito importante: Como o deck sumiu, limpamos nossa variável de controle
        deckSelecionadoId = null;

        // E então, atualizo a lista na tela imediatamente para o baralho sumir do modal
        await carregarDecks();

    } catch (erro) {
        console.error("Erro na comunicação com o servidor ao deletar deck:", erro);
        alert("Ocorreu um erro inesperado ao tentar se comunicar com o servidor.");
    }
}

// --- [ MEMBRO 3  - BLOCO 4 ]: FUNÇÕES AUXILIARES PARA A MANUTENÇÃO DO DASHBOARD (nova pagina3.html) ---

// Começo executando a busca e renderização dos Decks, assim que a página terminar de carregar:
document.addEventListener("DOMContentLoaded", () => {
    // Caso a tabela de revisão exista na tela, carrego os dados:
    if (document.getElementById("corpoTabelaDecksRevisao")) {
        carregarDashboardDecks();
        configurarBotoesDashboard();
    }
});

document.body.addEventListener('htmx:afterSwap', (event) => {
    if (document.getElementById("corpoTabelaDecksRevisao")) {
        carregarDashboardDecks();
        configurarBotoesDashboard();
    }
});

// Essa função abaixo serve para carregar adequadamente os Decks como linhas no novo Dashboard da nova pagina3.html:
async function carregarDashboardDecks() {
    const corpoTabela = document.getElementById("corpoTabelaDecksRevisao");
    const btnDeletar = document.getElementById("btnDeletarDeckRevisao");
    const btnRenomear = document.getElementById("btnRenomearDeckRevisao");
    
    if (!corpoTabela) return;
    
    try {
        // Começo tentando buscar os dados reais agregados do Back-end:
        const resposta = await fetch("/api/listar_decks");
        if (!resposta.ok) throw new Error("Erro ao listar decks do banco de dados.");
        
        const decks = await resposta.json();
        
        // Depois, limpo qualquer placeholder antigo que possa vir a existir:
        corpoTabela.innerHTML = "";
        deckSelecionadoId = null; 

        if (btnDeletar) btnDeletar.disabled = true; // E mantenho o botão de "Deletar Deck" bloqueado, até o usuário selecionar algum Deck.
        if (btnRenomear) btnRenomear.disabled = true; // O mesmo vale para o botão "Renomear Deck".
        
        // Caso ainda não tenha nenhum Deck cadastrado no BD, aviso isso ao usuário:
        if (decks.length === 0) {
            corpoTabela.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; color: #64748b; padding: 20px;">
                        Nenhum deck cadastrado. Clique em CRIAR DECK para começar a povoar.
                    </td>
                </tr>`;
            return;
        }
        
        // Se não, monto as linhas que representam os Decks no Dashboard:
        decks.forEach(deck => {
            const tr = document.createElement("tr");
            tr.className = "dashboard-tr-deck";
            tr.setAttribute("data-id", deck.id);
            
            tr.innerHTML = `
                <td class="td-deck-name">${deck.nome}</td>
                <td class="td-novos text-blue">${deck.novos}</td>
                <td class="td-revisar text-green">${deck.revisar}</td>
                <td class="td-qtd-total text-yellow">${deck.quantidade_total}</td>
            `;
            
            // E adiciono o evento de clique para seleção visual:
            tr.addEventListener("click", () => {
                // Para aplicar a seleção visual, primeiro removo a classe "selected" de todas as linhas:
                document.querySelectorAll(".dashboard-tr-deck").forEach(linha => {
                    linha.classList.remove("selected");
                });
                
                // E depois aplico ela somente na que o usuário clicou:
                tr.classList.add("selected");
                
                // Por fim, atualizo a variável global com o ID correto e ativo o botão DELETAR e RENOMEAR:
                deckSelecionadoId = deck.id;
                if (btnDeletar) btnDeletar.disabled = false;
                if (btnRenomear) btnRenomear.disabled = false;
            });

            // Além disso, se o usuário der um duplo clique, ele será redirecionado para a pagina4.html, e inicia a revisão usando o HTMX:
            tr.addEventListener("dblclick", () => {
                htmx.ajax('GET', `/estudo_revisao?deck_id=${deck.id}`, {
                    target: 'main', // Substitua pelo ID do elemento principal onde suas páginas carregam dentro da home.html (ex: #body, #main, #conteudo)
                    swap: 'innerHTML'
                });
                // Atualiza a URL do navegador:
                window.history.pushState({}, "", `/estudo_revisao?deck_id=${deck.id}`)
            });
            corpoTabela.appendChild(tr);
        });

        
    } catch (erro) {
        console.error("Erro ao povoar a tabela de decks:", erro);
    }
}

// Essa outra função configura os ouvintes de clique nos botões inferiores "CRIAR DECK" e "DELETAR DECK":
function configurarBotoesDashboard() {
    const btnCriar = document.getElementById("btnCriarDeckRevisao");
    const btnRenomear = document.getElementById("btnRenomearDeckRevisao");
    const btnDeletar = document.getElementById("btnDeletarDeckRevisao");

    const tituloModal = document.querySelector(".submodal-titulo");
    const subModal = document.getElementById("subModalCriarDeck");
    const inputNome = document.getElementById("novoNomeDeckInput");
    
    // O botão de Criar agora apenas abre o submodal que já havíamos construído na pagina2.html:
    if (btnCriar) {
        btnCriar.onclick = () => {
            modoSubModal = "criar"; // Define o modo do submodal
            if (tituloModal) tituloModal.textContent = "Criar novo Deck"; // Texto de criar
            
            if (subModal) {
                subModal.style.display = "flex";
                if (inputNome) {
                    inputNome.value = "";
                    inputNome.focus();
                }
            }
        };
    }

    // Agora, vem a lógica do botão "Renomear Deck":
    if (btnRenomear) {
        btnRenomear.onclick = () => {
            modoSubModal = "renomear"; 
            if (tituloModal) tituloModal.textContent = "Renomear Deck";
            
            if (subModal) {
                subModal.style.display = "flex";
                if (inputNome) { 
                    inputNome.value = ""; 
                    inputNome.focus(); 
                }
            }
        };
    }
    
    // O botão de deletar continua com o comportamento antigo dele, mas chamando carregarDashboardDecks():
    if (btnDeletar) {
        btnDeletar.onclick = async () => {
            if (!deckSelecionadoId) return;
            
            if (confirm("Tem certeza que deseja deletar este deck permanentemente?")) {
                const formData = new FormData();
                formData.append("deck_id", deckSelecionadoId);
                
                const resposta = await fetch("/api/deletar_deck", {
                    method: "POST",
                    body: formData
                });
                
                if (resposta.ok) {
                    carregarDashboardDecks(); // Atualizo a tabela do Dashboard
                }
            }
        };
    }
}

async function verificarVideo(event) {
    event.preventDefault(); 
    const input = document.querySelector('.url-input');
    const link = input ? input.value : null;
    if(!link) return;

    const btnLoad = document.querySelector('.btn-load');
    const textoOriginal = btnLoad.innerText;
    btnLoad.innerText = "VERIFICANDO...";
    btnLoad.disabled = true;

    try {
        const resposta = await fetch(`/api/legenda?url=${encodeURIComponent(link)}`);
        const jsonResponse = await resposta.json();

        if (!resposta.ok) {
            if (jsonResponse.tokens_restantes !== undefined) {
                atualizarInterfaceTokens(jsonResponse.tokens_restantes);
            }
            throw new Error(jsonResponse.detail || "Erro desconhecido ao carregar legenda.");
        }

        htmx.ajax('GET', `/legenda?link=${encodeURIComponent(link)}`, {target: 'main'}).then(() => {
            window.history.pushState(null, '', `/legenda?link=${encodeURIComponent(link)}`);
        });

    } catch (erro) {
        const erroModal = document.getElementById('erroModal');
        const erroText = document.getElementById('erro');
        if (erroModal && erroText) {
            erroText.innerText = erro.message;
            erroModal.style.display = "block";
        }
    } finally {
        if (btnLoad) {
            btnLoad.innerText = textoOriginal;
            btnLoad.disabled = false;
        }
    }
}


