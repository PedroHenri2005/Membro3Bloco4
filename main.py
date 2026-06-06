from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from youtube_transcript_api import YouTubeTranscriptApi 
# [ MEMBRO 3 - BLOCO 4 ]: Apenas para não haver confusão de nomes, a próxima linha mudou levemente. Eu explico melhor essa mudança na linha de import do SQLModel:
from requests import Session as RequestsSession
import re 

# Alguns novos imports serão necessários para implementar o Token Bucket e a Cache:
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from limits import parse

# [ MEMBRO 3 - BLOCO 4 ]: Mudei o nome do antigo database.py para cache.py, como está comentado no próprio arquivo cache.py.
# [ MEMBRO 3 - BLOCO 4 ]: Então, note que diferente da versão antiga do projeto, agora importo as funções salvar_na_cache e carregar_da_cache do arquivo cache.py, ao invés do database.py:
from cache import salvar_na_cache, carregar_da_cache

# [ MEMBRO 3 - BLOCO 4 ]: Para configurar o Banco de Dados e a Engine, será necessário:
from contextlib import asynccontextmanager # [ MEMBRO 3 - BLOCO 4 ]: Servirá para ligar e desligar o servidor.
from sqlmodel import SQLModel, create_engine, select, Session, or_ # [ MEMBRO 3 - BLOCO 4 ]: O SQLModel também possui uma classe chamada Session, assim como requests lá em cima. Por isso, renomeei o de cima.
from models import Deck, Card # [ MEMBRO 3 - BLOCO 4 ]: É no models.py que definimos os modelos de Decks e Cards, e agora vamos importar eles.

# [ MEMBRO 3 - BLOCO 4 ]: Para a manutenção das datas de revisão dos Cards, será necessário:
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# Imports necessários para a geração de áudio (Waves)
import yt_dlp
import asyncio
import os
import subprocess
import traceback

# [ MEMBRO 3 - BLOCO 4 ]: Configuração do BD com SQLite:
arquivo_sqlite = "estudos.db"
url_sqlite = f"sqlite:///{arquivo_sqlite}"

# [ MEMBRO 3 - BLOCO 4 ]: Criação da Engine do BD:
engine = create_engine(url_sqlite)

def criar_db_e_tabelas():
    """Cria o arquivo estudos.db e os modelos de Decks e Cards, caso não existam ainda."""
    SQLModel.metadata.create_all(engine)
    print("O Banco de Dados contendo os modelos de Decks e Cards foi criado e está pronto para ser povoado.")

# [ MEMBRO 3 - BLOCO 4 ]: É aqui ocorre a ativação e desativação do servidor (lifespan):
@asynccontextmanager
async def initFunction(app: FastAPI):
    # [ MEMBRO 3 - BLOCO 4 ]: Executado exatamente no momento em que o servidor liga:
    criar_db_e_tabelas()
    yield
    # [ MEMBRO 3 - BLOCO 4 ]: Executado no momento em que o servidor desliga:
    print("Servidor finalizado adequadamente.")

# Começamos definindo o limitador:
# Ele servirá para restringir a quantidade de requisições que o usuário poderá fazer ao Youtube
limitador = Limiter(key_func=get_remote_address)
# [ MEMBRO 3 - BLOCO 4 ]: Colocando o lifespan junto com o limitador:
app = FastAPI(lifespan=initFunction)
app.state.limiter = limitador

# DICIONÁRIO DE CADEADOS PARA DOWNLOADS SIMULTÂNEOS
download_locks = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #permitindo qualquer site
    allow_methods=["*"], #quais "verbos" HTTP o site pode acessar, nesse caso permitindo todos
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory=["templates", "templates/Partials"])

# para evitar bloqueios cookie do Youtube
http_session = RequestsSession() # [ MEMBRO 3 - BLOCO 4 ]: Agora, como renomeei a classe Session do requests para RequestsSession, essa linha mudou um pouco.

# ROTAS E NAVEGAÇÃO

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "pagina":"/pagina1"
            }
        )

@app.get("/pagina1", response_class=HTMLResponse)
async def pag1(request: Request):
    if (not "HX-Request" in request.headers):
        return templates.TemplateResponse(
            request,
            "home.html",
            context={
                "pagina":"/pagina1",
            }
        )
    return templates.TemplateResponse(request, "pagina1.html")

@app.get("/legenda", response_class=HTMLResponse)
async def pagina2(request: Request):
    if (not "HX-Request" in request.headers):
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"pagina": "/legenda"}
        )
    return templates.TemplateResponse(
            request=request, 
            name="pagina2.html", 
        ) 

@app.get("/revisao",response_class=HTMLResponse)
async def revisar(request:Request):
    if (not "HX-Request" in request.headers):
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"pagina": "/revisao"}
        )
    return templates.TemplateResponse(
            request=request, 
            name="pagina3.html", 
        )

# [ MEMBRO 3  - BLOCO 4 ]: ROTA NOVA DE NAVEGAÇÂO PARA ABRIR A pagina4.html (tela de revisão dos Decks de fato):

@app.get("/estudo_revisao", response_class=HTMLResponse)
async def estudo_revisao(request: Request):
    # Se o usuário tentar acessar direto pela URL sem o HTMX (F5):
    if (not "HX-Request" in request.headers):
        # Pegamos o valor completo dos parâmetros da URL para não perder o deck_id:
        query_string = str(request.url.query)
        pagina_com_parametros = f"/estudo_revisao?{query_string}" if query_string else "/estudo_revisao"
        
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"pagina": pagina_com_parametros}
        )
        
    # Se for uma requisição interna do HTMX, entrega apenas o bloco da pagina4.html:
    return templates.TemplateResponse(
        request=request, 
        name="pagina4.html"
    )

# ROTAS DE API E DADOS

def limpar_url_extrair_id(url: str):
    padrao = r'(?:v=|/|be/)([0-9A-Za-z_-]{11})'
    encaixou = re.search(padrao, url)
    if encaixou:
        return encaixou.group(1)
    else:
        return None

# GET para pegar as legendas, adaptado para a Cache e o Token Bucket:
# [ MEMBRO 3 - BLOCO 4 ]: E agora também adaptado para legendas automáticas e para extrair o título dos vídeos (apenas para ficar mais informativo para o usuário):

@app.get("/api/legenda")
async def obter_legenda(request: Request, url: str):
    video_id = limpar_url_extrair_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL do YouTube inválida.")
    
    # Aqui vem a parte mais importante: 
    # Definir quantos tokens o usuário tem, para cada certo período de tempo.
    limite = parse("5/5 minute") # Tomei a liberdade de fornecer inicialmente 5 tokens para o usuário poder gastar.
    # A cada 5 minutos, a quantidade de tokens do usuário(bucket) reseta para 5 novamente.
    # Se achar 5 minutos demais, basta trocar o segundo 5 da linha de código acima pela quantidade de minutos que desejar =)
    ip_do_usuario = get_remote_address(request)
    cache = carregar_da_cache(video_id)

    if cache:
        # Se o vídeo estiver na cache, não é necessário descontar um token, pois puxamos as legendas da memória:
        dados_do_usuario = limitador.limiter.get_window_stats(limite, ip_do_usuario, "obter_legenda")
        tokens_restantes = dados_do_usuario.remaining

        # [ MEMBRO 3 - BLOCO 4 ]:

        # Antes, a cache salvava as legendas como uma lista de frases. Agora, temos a informação sobre o tipo da legenda (manual/automática) sendo adicionada.
        # Então, para garantir que um vídeo que esteja no formato antigo dentro cache (lista de frases) seja adaptado para o novo formato (dicionário: tipo da legenda + lista de frases), será necessário:
        # Como o que está dentro da cache agora será um dicionário, basta extrair esse tipo, juntamente com as legendas:
        era_manual = cache.get("legenda_manual", True)
        legendas = cache.get("legendas", [])

        # [ MEMBRO 3 - BLOCO 4 ]: 
        # Adicionemos uma nova funcionalidade: Extrair o título do vídeo do Youtube que o usuário está estudando.
        # Assumindo que existe o título do vídeo no dicionário armazenado dentro da Cache, podemos tentar extrair ele:
        titulo_salvo = cache.get("titulo_video")

        # [ MEMBRO 3 - BLOCO 4 ]: 
        # Quando clicamos no botão para usar esse método GET, é desejável que ele seja utilizado apenas uma vez. Mas, não é isso que acontece na prática.
        # Como é possível ver no terminal quando esse código roda, o HTMX acaba fazendo requisições extras, mesmo apertando o botão uma única vez.
        # Isso pode criar um cenário de duas requisições praticamente simultâneas (condição de corrida). 
        # Dessa forma, o título pode acabar sendo lido de forma errônea.
        # Se não houver título salvo dentro da Cache, ou se esse título dummy estiver lá:
        if not titulo_salvo or titulo_salvo == "Vídeo do YouTube":
            try:
                # É possível extrair a URL limpa do vídeo (limpa no sentido de não ter marcações de tempo ou algo assim):
                url_limpa_youtube = f"https://www.youtube.com/watch?v={video_id}"
                # E então, podemos usar a URL oEmbed para tentar extrair o título. Essa URL é um formato que o Youtube disponibiliza para ter acesso aos metadados do vídeo.
                # No nosso caso, a informação de interesse é o título, e queremos que isso venha no formato JSON:
                url_oembed = f"https://www.youtube.com/oembed?url={url_limpa_youtube}&format=json"
                # E então, a requisição do Youtube para extrair os metadados:
                resposta_oembed = http_session.get(url_oembed)

                if resposta_oembed.status_code == 200:
                    # Aqui, se tudo der certo, podemos pegar o JSON que o Youtube forneceu como resposta e procurar o atributo "title", e depois guardar na Cache:
                    titulo_salvo = resposta_oembed.json().get("title", "Vídeo do YouTube")
                    cache["titulo_video"] = titulo_salvo
                    salvar_na_cache(video_id, cache)

                else:
                    titulo_salvo = "Vídeo do YouTube"

            except Exception:
                titulo_salvo = "Vídeo do YouTube"

        # [ MEMBRO 3 - BLOCO 4 ]: Com a variável era_manual, é possível lançar um aviso no Back-End para informar que as legendas do vídeo estavam na Cache, e também o tipo de sua legenda:
        if era_manual:
            tipo_legenda = "MANUAL"
        else:
            tipo_legenda = "AUTOMÁTICA - Erros de transcrição são possíveis nesse caso"

        print(f"Tipo de legenda (Cache): {tipo_legenda} | Título: {titulo_salvo}")

        # [ MEMBRO 3 - BLOCO 4 ]: Retornamos os dados da cache, o saldo de tokens, a característica da legenda, o título e um aviso que será usado no Front-End, idêntico ao do Back-End:
        return JSONResponse(content={
            "dados": legendas,
            "tokens_restantes": tokens_restantes,
            "legenda_manual": era_manual,
            "titulo_video": titulo_salvo,
            "aviso_legenda": f"Tipo de legenda (Cache): {tipo_legenda} | Título: {titulo_salvo}"
        })
        
    # Se o usuário gastar todos os seus tokens e zerar seu saldo, um JSON avisando isso é mostrado para o usuário:
    if not limitador.limiter.hit(limite, ip_do_usuario, "obter_legenda"):
        return JSONResponse(
            status_code=429,
            content={"detail": "O limite de 5 tokens foi atingido. Espere 5 minutos para ter mais 5 tokens.", "tokens_restantes": 0}
        )
    
    # Obtendo novamente o saldo de tokens do usuário:
    dados_do_usuario = limitador.limiter.get_window_stats(limite, ip_do_usuario, "obter_legenda")
    tokens_restantes = dados_do_usuario.remaining

    # Se o código chegar nas próximas linhas, é porque o vídeo é novo. Logo, 1 token deve ser cobrado do usuário.
    # Como a ID do vídeo não está na memória e usuário ainda tem tokens para gastar nesse ponto do código, aí sim uma requisição ao Youtube deve ser feita:
    try:
        youtube_api = YouTubeTranscriptApi(http_client=http_session)
        lista_de_legendas = youtube_api.list(video_id)
        # [ MEMBRO 3 - BLOCO 4 ]: Se o vídeo não estiver na Cache, começamos definindo o título dummy "Vídeo do Youtube":
        titulo_video = "Vídeo do YouTube"

        try:
            # [ MEMBRO 3 - BLOCO 4 ]: Aqui, fazemos o mesmo processo de antes para extrair o título do vídeo do Youtube:
            url_limpa_youtube = f"https://www.youtube.com/watch?v={video_id}"
            url_oembed = f"https://www.youtube.com/oembed?url={url_limpa_youtube}&format=json"
            resposta_oembed = http_session.get(url_oembed)

            if resposta_oembed.status_code == 200:
                titulo_video = resposta_oembed.json().get("title", "Vídeo do YouTube")
            else:
                print(f"oEmbed respondeu com status {resposta_oembed.status_code} para o ID {video_id}")

        except Exception as e:
            print(f"Erro ao buscar oEmbed: {e}")
            pass

        # [ MEMBRO 3 - BLOCO 4 ]:

        # Nessa etapa do projeto, é desejável que as legendas automáticas também sejam uma opção, além das manuais que já estão implementadas.
        # Porém, se a legenda extraída do vídeo for automática, um aviso no Back-End e Front-End deve ser lançado avisando que podem haver erros nela, diferente das manuais.
        # Inicialização das variáveis que serão usadas:
        legenda_objeto = None # Variável que guardará as legendas em si (sejam elas manuais ou automáticas).
        tem_legenda_manual = True # Variável que indicará se as legendas são manuais ou automáticas. Suponhamos inicialmente que um vídeo genérico possua legendas manuais.

        try:
            # Primeiro, vou tentar extrair as legendas manuais do vídeo. Se elas existirem, essa linha será suficiente para extraí-las:
            legenda_objeto = lista_de_legendas.find_manually_created_transcript(['en'])
            print(f"Tipo de legenda: MANUAL | Título: {titulo_video}")

        except Exception:

            try:
                # Se falhar, isso significa que as legendas manuais não existem. Então, como segunda opção, tentarei extrair as legendas automáticas:
                legenda_objeto = lista_de_legendas.find_generated_transcript(['en'])
                tem_legenda_manual = False # Aviso ao sistema que essa legenda não é manual.
                print(f"Tipo de legenda: AUTOMÁTICA - Erros de transcrição são possíveis nesse caso. | Título: {titulo_video}")

            except Exception:
                # Se falhar novamente, isso significa que não há legendas em inglês disponíveis para esse vídeo específico:
                raise HTTPException(status_code=404, detail="O vídeo não possui nenhuma legenda em inglês disponível")
        
        blocos_brutos = legenda_objeto.fetch()
        legendas_formatadas = []
        texto_anterior = ""

        for bloco in blocos_brutos:
            texto_limpo = " ".join(bloco.text.split())
            
            # Aqui, vem a parte da limpeza das legendas. Os objetivos são:
            # Limpar blocos de duração pequena demais (duração menor ou igual a 1 segundo).
            # Remover legendas repetidas.

            if texto_limpo and bloco.duration >= 1.0 and texto_limpo != texto_anterior:
                tempo_fim_calculado = bloco.start + bloco.duration
                legendas_formatadas.append({
                    "id_do_bloco": len(legendas_formatadas),
                    "texto_limpo": texto_limpo,    
                    "tempo_inicio": bloco.start,
                    "tempo_fim": tempo_fim_calculado
                })

                texto_anterior = texto_limpo

        # É necessário então sobrescrever a cache com o novo vídeo:
        # [ MEMBRO 3  - BLOCO 4 ]: Agora, além de guardar somente as legendas_formatadas (como era na versão antiga), vou guardar também a varíavel tem_legenda_manual e o titulo_video:

        dados_para_salvar = {
            "legendas": legendas_formatadas,
            "legenda_manual": tem_legenda_manual,
            "titulo_video": titulo_video
        }

        salvar_na_cache(video_id, dados_para_salvar)

        # Para finalizar, antes de retornar o JSON completo, falta apenas o texto de aviso para o Front-End, que será baseado no tipo de legenda capturado:
        if tem_legenda_manual:
            texto_aviso = f"Tipo de legenda: MANUAL | Título: {titulo_video}"
        else:
            texto_aviso = f"Tipo de legenda: AUTOMÁTICA - Erros de transcrição são possíveis nesse caso. | Título: {titulo_video}"

        # Depois, basta retornar as legendas, os tokens restantes que o usuário possui, o tipo de legenda, o título do vídeo e por fim o aviso da legenda:
        return JSONResponse(content={
            "dados": legendas_formatadas,
            "tokens_restantes": tokens_restantes,
            "legenda_manual": tem_legenda_manual,
            "titulo_video": titulo_video,
            "aviso_legenda": texto_aviso
        })

    except Exception as e:
        mensagem_de_erro = str(e)
        if "Could not retrieve a transcript" in mensagem_de_erro:
            raise HTTPException(status_code=404, detail="Vídeo sem legendas disponíveis em inglês.") #  [ MEMBRO 3 - BLOCO 4 ]:  Mensagem de erro adaptada, pois agora o projeto aceita legendas automáticas também.
        print(f"Erro técnico: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar legendas.") 


# --- INTEGRAÇÃO DO SISTEMA DE ÁUDIO (WAVES) ---

def _baixar_audio_sync(url: str, audio_base: str):
    """Executa o download do yt_dlp de forma síncrona — chamado via executor."""
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": audio_base,
        "quiet": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
        ydl.download([url])

def _cortar_audio_sync(inicio_f: float, fim_f: float, audio_base: str, bloco_wav: str):
    """Executa o FFmpeg de forma síncrona via executor para driblar o erro do Windows."""
    comando = [
        "ffmpeg",
        "-y",
        "-ss", str(inicio_f),
        "-to", str(fim_f),
        "-i", audio_base,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "1",
        bloco_wav
    ]
    # Roda o comando escondendo os logs do ffmpeg no terminal
    resultado = subprocess.run(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg encerrou com código {resultado.returncode}")


@app.get("/api/audio")
async def obter_audio(url: str, inicio: str, fim: str):
    os.makedirs("audio", exist_ok=True)

    try:
        inicio_f = float(inicio)
        fim_f = float(fim)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Parâmetros 'inicio' e 'fim' devem ser números.")

    video_id = limpar_url_extrair_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL do YouTube inválida.")

    audio_base = f"audio/{video_id}.m4a"
    bloco_wav = f"audio/{video_id}_{inicio_f:.2f}_{fim_f:.2f}.wav"

    # CACHE DO BLOCO
    if os.path.exists(bloco_wav):
        print("CACHE HIT BLOCO")
        return FileResponse(bloco_wav, media_type="audio/wav")

    loop = asyncio.get_event_loop()

    # --- PROTEÇÃO CONTRA RACE CONDITION ---
    
    # Cria um cadeado específico para este vídeo, se não existir
    if video_id not in download_locks:
        download_locks[video_id] = asyncio.Lock()

    # Só permite que uma requisição por vez entre neste bloco
    async with download_locks[video_id]:
        # Verifica NOVAMENTE se o arquivo existe (pois a requisição anterior pode ter acabado de criá-lo)
        if not os.path.exists(audio_base):
            print(f"BAIXANDO ÁUDIO BASE ({video_id})...")
            try:
                await loop.run_in_executor(None, _baixar_audio_sync, url, audio_base)
            except Exception as e:
                print("=== ERRO AO BAIXAR ÁUDIO ===")
                traceback.print_exc()
                raise HTTPException(status_code=500, detail="Erro ao baixar áudio base.")
                
    # --- FIM DA PROTEÇÃO ---

    # CORTE DO BLOCO — Todas as requisições podem cortar o áudio base simultaneamente
    try:
        print(f"GERANDO BLOCO {inicio_f:.2f} -> {fim_f:.2f}")
        await loop.run_in_executor(None, _cortar_audio_sync, inicio_f, fim_f, audio_base, bloco_wav)

        return FileResponse(bloco_wav, media_type="audio/wav")

    except Exception as e:
        print("=== ERRO AO GERAR BLOCO ===")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Erro ao gerar bloco.")

# --- [ MEMBRO 3 - BLOCO 4 ]: ROTAS PARA SALVAMENTO DE CARDS E DECKS NO NOVO BANCO DE DADOS ---

# Vamos começar implementando a base para lista de Decks que se atualizará dinamicamente no modal de escolha de Decks.
# Naturalmente, será necessária uma rota para retornar a lista de todos os Decks cadastrados nesse BD:

# ROTA 1 - Retorna a lista de todos os Decks do BD:

@app.get("/api/listar_decks")
def listar_decks():
    # Começo obtendo o momento de agora:
    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)

    with Session(engine) as session:
        # Depois, basta buscar todos os Decks cadastrados no BD:
        decks = session.exec(select(Deck)).all() 
        resultado = []

        for deck in decks:
            # Aproveito para contar a quantidade de Cards total nesse Deck (será útil para a nova pagina3.html):
            total_cards = session.exec(
                select(Card).where(Card.deck_id == deck.id)
            ).all()

            qtd_total = len(total_cards)

            # Também será útil para o Dashboard da pagina3.hmtl contar Cards "Novos": aqueles que ainda têm quantidade de revisões feitas igual a 0.
            qtd_novos = len([
                c for c in total_cards 
                if getattr(c, 'revisao', 0) == 0
            ])

            # Por fim, a última informação que será boa para o Dashboard é contar os Cards que precisam ser revisados.
            qtd_revisar = 0
            for c in total_cards:
                # Se o Card tiver uma quantidade de revisões maior que 0, isso significa que ele não é novo:
                if getattr(c, 'revisao', 0) > 0:
                    # Então, obtemos a data da próxima revisão desse Card:
                    dt_revisao = getattr(c, 'data_proxima_revisao', None)
                    if dt_revisao:
                        # Se a data da próxima revisão desse Card já tiver passado (ou seja, se o momento for <= agora), então esse Card precisa ser revisado novamente.
                        if dt_revisao.replace(tzinfo=None) <= agora:
                            # Por isso, a quantidade de revisões dele vai ser incrementada (isso vai ser mostrado no Dashboard de Decks).
                            qtd_revisar += 1

            resultado.append({
                "id": deck.id,
                "nome": deck.nome,
                "novos": qtd_novos,
                "revisar": qtd_revisar, 
                "quantidade_total": qtd_total
            })
            
        return resultado

# ROTA 2 - Cria um Deck novo:

@app.post("/api/criar_deck")
def criar_deck(nome: str = Form(...)):
    with Session(engine) as session:
        # Logo abaixo, vem uma lógica para permitir que, embora o usuário crie Decks de mesmo nome, seja adicionado um índice ao lado, para diferenciá-los:
        # Ex: Se o usuário criar 3 Decks com nome Baralho, eu quero que o primeiro tenha nome Baralho.
        # O segundo tenha nome Baralho (2), o terceiro Baralho (3), e assim por diante.

        # Começo removendo espaços que o usuário possa ter digitado nas pontas:
        nome_base = nome.strip()
        
        # Buscamos no banco se já existe algum Deck com esse nome exato:
        existe_exato = session.exec(
            select(Deck).where(Deck.nome == nome_base)
        ).first()

        # Se não existe, salvo direto no BD:
        if not existe_exato:
            novo_deck = Deck(nome=nome_base)
            session.add(novo_deck)
            session.commit()
            session.refresh(novo_deck)
            return JSONResponse(
                status_code=200,
                content={"status": "sucesso", "id": novo_deck.id, "nome": novo_deck.nome}
            )

        # Se o nome exato já existe, precisamos calcular o próximo índice.
        # Buscamos todos os decks que começam com o nome base (o nome base de "Baralho (2)" e "Baralho (3)" seria "Baralho", por exemplo), para checar os números já usados:
        decks_parecidos = session.exec(
            select(Deck).where(Deck.nome.like(f"{nome_base}%"))
        ).all()

        # Guardo todos os nomes existentes in um conjunto (set) para fazer uma busca:
        nomes_existentes = {d.nome for d in decks_parecidos}

        contador = 2
        nome_final = f"{nome_base} ({contador})"

        # E então incrementamos o índice até o nome completo do Deck não constar no conjunto de Decks que já estão salvos no BD: 
        while nome_final in nomes_existentes:
            contador += 1
            nome_final = f"{nome_base} ({contador})"

        # Agora sim, é possível salvar esse Deck novo:
        novo_deck = Deck(nome=nome_final)
        session.add(novo_deck)
        session.commit()
        session.refresh(novo_deck)

        return JSONResponse(
            status_code=200,
            content={"status": "sucesso", "id": novo_deck.id, "nome": novo_deck.nome}
        )

# ROTA 3 - Deleção de Deck pelo ID:
@app.post("/api/deletar_deck")
def deletar_deck(deck_id: int = Form(...)):
    with Session(engine) as session:
        # Começo buscando o deck diretamente pelo ID:
        deck = session.get(Deck, deck_id)
        
        # Se o Deck não for encontrado (ex: já deletado por outra aba):
        if not deck:
            return JSONResponse(
                status_code=404,
                content={"status": "erro", "mensagem": "Deck não encontrado."}
            )
        
        try:
            # Depois disso, tento remover o Deck do BD (lembrando que, segundo o models.py, quando um Deck é deletado, todos os seus Cards são deletados junto):
            session.delete(deck)
            session.commit()
            
            return JSONResponse(
                status_code=200,
                content={"status": "sucesso", "mensagem": f"Deck '{deck.nome}' deletado com sucesso!"}
            )
            
        except Exception as e:
            session.rollback()
            return JSONResponse(
                status_code=500,
                content={"status": "erro", "mensagem": f"Erro interno no servidor: {str(e)}"}
            )

# ROTA 4 - Salvando o Card num certo Deck selecionado pelo usuário:
@app.post("/salvar_card")
# Aqui há a assinatura da função. Passamos todos os dados do bloco de legenda necessários para a criação do Card:
def salvar_card_bd(
    request: Request,
    deck_id: int = Form(...), # O ID do Deck em que quero salvar o Card.
    video_id: str = Form(...), # O ID de 11 dígitos do Youtube que vem da URL do vídeo.  
    texto_legenda: str = Form(...), # O conteúdo do Card propriamente dito, ou seja, um pedaço da legenda do vídeo.
    start_time: float = Form(...), # O tempo de ínicio desse bloco de legenda que será salvo.
    end_time: float = Form(...) # Analogamente, o tempo de fim.
):
    with Session(engine) as session:
        
        deck = session.get(Deck, deck_id)
        if not deck:
            raise HTTPException(status_code=404, detail="O baralho selecionado não foi encontrado.")
        
        # Seria bom se o sistema evitasse criar múltiplos Cards idênticos para o mesmo Deck. Para evitar isso:
        query_duplicado = select(Card).where(
            Card.deck_id == deck_id, 
            Card.texto_legenda == texto_legenda
        )
        card_existente = session.exec(query_duplicado).first()
        
        # Então, se acharmos um Card igual ao que o usuário tentou salvar:
        if card_existente:
            return JSONResponse(
                status_code=200, 
                content={
                    "status": "duplicado",
                    "mensagem": "Este card já foi salvo anteriormente nesse Deck.",
                 }
            )
 
        # A essa altura, o Deck do vídeo em questão com certeza existe. Logo, podemos salvar o Card, que será associado ao Deck pela propriedade video_id:
        novo_card = Card(
            texto_legenda=texto_legenda,
            start_time=start_time,
            end_time=end_time,
            video_id=video_id,
            deck_id=deck_id
        )

        session.add(novo_card)
        session.commit()
        print(f"Novo Card salvo: {texto_legenda}")

        return JSONResponse(
            status_code=200, 
            content={
                "status": "sucesso",
                "mensagem": "Card salvo com sucesso.",
                  }
        )

# ROTA 5 - Renomeia um Deck existente pelo ID:
@app.post("/api/renomear_deck")
def renomear_deck(deck_id: int = Form(...), nome: str = Form(...)):
    with Session(engine) as session:
        # Começo buscando o deck diretamente pelo ID fornecido:
        deck = session.get(Deck, deck_id)
        
        # Se o Deck não for encontrado no Banco de Dados:
        if not deck:
            return JSONResponse(
                status_code=404,
                content={"status": "erro", "mensagem": "Deck não encontrado para renomeação."}
            )
        
        try:
            # Removo espaços extras nas pontas que o usuário possa ter digitado:
            nome_limpo = nome.strip()
            
            # Caso o usuário envie um nome vazio, podemos definir um padrão:
            if not nome_limpo:
                nome_limpo = "Deck"

            # Aplicando a mesma lógica de índices automáticos que foi feita para criação de Decks de mesmo nome:
            existe_exato = session.exec(select(Deck).where(Deck.nome == nome_limpo, Deck.id != deck_id)).first()
            if existe_exato:
                decks_parecidos = session.exec(select(Deck).where(Deck.nome.like(f"{nome_limpo}%"), Deck.id != deck_id)).all()
                nomes_existentes = {d.nome for d in decks_parecidos}
                contador = 2
                nome_final = f"{nome_limpo} ({contador})"
                while nome_final in nomes_existentes:
                    contador += 1
                    nome_final = f"{nome_limpo} ({contador})"
                nome_limpo = nome_final

            # Atualizo a propriedade de nome do objeto Deck encontrado:
            deck.nome = nome_limpo
            
            # Adiciono a modificação na sessão e efetivo a alteração no Banco de Dados:
            session.add(deck)
            session.commit()
            session.refresh(deck)
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": "sucesso", 
                    "mensagem": "Deck renomeado com sucesso!",
                    "id": deck.id,
                    "nome": deck.nome
                }
            )
            
        except Exception as e:
            # Caso ocorra qualquer erro na transação de nomes, desfazemos as alterações na sessão:
            session.rollback()
            return JSONResponse(
                status_code=500,
                content={"status": "erro", "mensagem": f"Erro interno no servidor ao renomear: {str(e)}"}
            )

# ROTA 6 - Aqui, faço a busca de todos os Cards do Deck que precisam ser revisados (ou seja, somente os que são das categorias "Novos" ou "Revisar"):
@app.get("/api/revisar_deck/{deck_id}")
def revisar_deck(deck_id: int):
    with Session(engine) as session:
        # Começo obtendo o horário atual:
        agora = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
        
        # Depois, busco os cards do deck aplicando os filtros necessários:
        cards = session.exec(
            select(Card)
            .where(Card.deck_id == deck_id)
            .where(
                or_(
                    Card.revisao == 0, # Cards "Novos" que acabaram de serem salvos no Deck.
                    Card.data_proxima_revisao <= agora # Cards mais velhos cuja data de revisão já expirou, entram na categoria "Revisar".
                )
            )
        ).all()
        
        # Então, monto o retorno JSON:
        resultado = []
        for card in cards:
            resultado.append({
                "id": card.id,
                "texto_legenda": card.texto_legenda,
                "start_time": card.start_time,
                "end_time": card.end_time,
                "video_id": card.video_id
            })
            
        return resultado

# ROTA 7 - Rota para atualizar a data_proxima_revisao de um certo Card:
@app.post("/api/atualizar_revisao/{card_id}/{dificuldade}")
def atualizar_revisao(card_id: int, dificuldade: str):
    with Session(engine) as session:
        # Começo buscando o Card no BD: 
        card = session.get(Card, card_id)
        if not card:
            raise HTTPException(status_code=404, detail="Card não encontrado")
        
        agora = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
        
        # Depois, aplico a lógica dos multiplicadores que serão aplicados pelo usuário ao clicar em "Fácil", "Médio" e "Difícil":
        # Aqui, coloquei multiplicadores pequenos, apenas para testar se os Cards a serem revisados apareciam corretamente no Dashboard da pagina3.html. São eles:

        # MULTIPLICADORES:

        # "Fácil": 10 segundos após a revisão, a data de revisão desse Card já expira, e ele deve ser revisado de novo.
        # "Médio": 30 segundos.
        # "Difícil": 60 segundos.

        # Testando ao alternar entre a pagina3.html e a pagina4.html, assim que um Card "Novo" é revisado na pagina4.html, basta voltar para a pagina3.html e ver que a categoria "Novo" será decrementada, por conta desse Card.
        # Depois de esperar pelo tempo estipulado pela dificuldade que esse Card foi avaliado e recarregar a página, já é possível ver que a categoria "Revisar" foi incrementada por conta desse Card, e já será possível revisar ele de novo.
        # (OBS): Se quiser testar com outras datas de revisão (para minutos ou até dias), basta mudar o argumento das funções timedelta abaixo:

        if dificuldade == "facil":
            card.data_proxima_revisao = agora + timedelta(seconds=10)
        elif dificuldade == "medio":
            card.data_proxima_revisao = agora + timedelta(seconds=30)
        elif dificuldade == "dificil":
            card.data_proxima_revisao = agora + timedelta(seconds=60)
        else:
            raise HTTPException(status_code=400, detail="Dificuldade inválida")
        
        # Depois da revisão do Card, é necessário incrementar a quantidade de revisões feitas nele:
        card.revisao += 1
        
        session.add(card)
        session.commit()
        session.refresh(card)
        
        return {
            "status": "sucesso", 
            "card_id": card.id, 
            "nova_revisao": card.data_proxima_revisao.isoformat(),
            "numero_revisoes": card.revisao
        }

# ROTA 8 - Rota para deletar o Card de um certo Deck (será usado somente no ícone de lixeira na pagina4.html, onde o usuário revisa os Cards de um Deck):
@app.delete("/api/deletar_card/{card_id}")
def deletar_card_revisao(card_id: int):
    with Session(engine) as session:
        card = session.get(Card, card_id)
        if not card:
            raise HTTPException(status_code=404, detail="Card não encontrado no servidor.")
        try:
            session.delete(card)
            session.commit()
            return {"status": "sucesso", "mensagem": "Card excluído com sucesso."}
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=f"Erro ao deletar do banco: {str(e)}")

 
