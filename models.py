# [ MEMBRO 3 - BLOCO 4 ]: Aqui é onde ficarão as classes que serão usadas para salvar os Cards de revisão, que serão organizados em Decks:
from datetime import datetime, timezone
from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel
from zoneinfo import ZoneInfo

# Modelo para os Decks:
class Deck(SQLModel, table=True):
    """Modelo de baralhos, agrupando cartões criados pelo usuário."""
    id: Optional[int] = Field(default=None, primary_key=True) 
    nome: str = Field(min_length=1, index=True, unique=True) 

    cards: List["Card"] = Relationship(back_populates="deck", cascade_delete = True) # Aqui, relaciono o Deck com todos os Cards dele.　Se o Deck for deletado, todos os seus Cards também são.

# Modelo para os Cards:
class Card(SQLModel, table=True):
    """Modelo dos Cards salvos para revisão espaçada, vinculados a um Deck e rastreando o vídeo de origem."""
    id: Optional[int] = Field(default=None, primary_key=True)
    texto_legenda: str = Field(min_length=1)

   # Rastreamento do vídeo do YouTube que deu origem a esse Card:

    video_id: str = Field(index=True) # Aqui, guardo o ID de 11 dígitos do Youtube que vem da URL do vídeo.
    start_time: float # Tempo de vídeo em que começa o texto de legenda do Card no vídeo.
    end_time: float # Tempo de vídeo em que terminar o texto de legenda do Card no vídeo.

    # Por padrão, a data de criação e de revisão de um Card novo será o momento atual:
    data_criacao: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None))
    data_proxima_revisao: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None))

    # Registra quantas vezes o card já foi revisado (começa em 0 = Novo):
    revisao: int = Field(default=0)

    # Chave estrangeira ligando o Card ao seu respectivo Deck customizado:
    deck_id: int = Field(foreign_key="deck.id", index=True)
    deck: Optional[Deck] = Relationship(back_populates="cards")

