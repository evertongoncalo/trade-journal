# Trade Journal

App web local para **analisar ativos (ações, cripto, forex) e registrar as próprias decisões**, para descobrir
se "setup + decisão humana" é viável. Nada é automático: o app nunca opera. A pergunta central não é lucro,
é **acerto da tese e qualidade de decisão**.

> Ferramenta de apoio à decisão do próprio usuário; não é recomendação de investimento.
> Probabilidades mostradas são frequências históricas, não garantias.

Desenho completo: [docs/ESPECIFICACAO.md](docs/ESPECIFICACAO.md).

## Status (v0.2)

| Pronto | Ainda não |
|---|---|
| Ficha do ativo: gráfico (widget do TradingView), indicadores, saúde dos dados | Funil / radar diário com setups |
| Inclinação probabilística (P(alta em N dias \| estado) com amostra, intervalo e base) | Botão de IA (lentes) e memória/pós-mortem |
| Diário: registro, acompanhamento automático do resultado (alvo × invalidação × expirada), saída antecipada | Alertas de preço |
| Acerto da tese por decisão (entrei / não entrei / observando) | Revisão do acerto por bloco e por lente |
| **Painel de correlação (só código):** S&P 500 e DXY fixos + ~40 candidatos, alinhados às 16h de Nova York, estabilidade, parecer e 3 gráficos | |

### Painel de correlação

Na primeira vez, clique em **Atualizar universo** (30 s a 2 min): ele baixa o universo de candidatos (índices, juros, VIX,
commodities, cripto, forex, ETFs de setor) e guarda no SQLite local. Cada ativo é amostrado a partir de dados de 1 hora
na última barra que fecha às 16h de Nova York, para que forex, cripto e bolsas sejam comparados no mesmo instante.
Relações mecânicas (par de forex com moeda em comum, DXY × par com USD, ação × ETF do próprio setor) ficam marcadas e
escondidas por padrão. A janela é de ~2 anos (limite do dado de 1 hora do Yahoo).

## Como rodar (Windows)

Requisitos: Python 3.12+ (testado com 3.14) e Node 20+.

```bat
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
cd ..\frontend
npm install
npm run build
cd ..
iniciar.cmd
```

Abra <http://127.0.0.1:8765>. Os dados do diário ficam em `data/journal.db` (fora do git; faça backup desse arquivo).

### Desenvolvimento

```bat
cd backend
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8765
```
```bat
cd frontend
npm run dev
```
O Vite (<http://localhost:5173>) encaminha `/api` para o backend.

### Testes

```bat
cd backend
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

## Estrutura

```
backend/app/
  providers/   fontes de preço atrás de uma interface comum (Yahoo, Binance) + símbolos
  analysis/    indicadores (RSI/ATR de Wilder, MACD, Bollinger) e inclinação probabilística
  journal/     avaliação do plano de uma tese (alvo × invalidação × horizonte, em R)
  routes/      API (/api/asset, /api/journal)
frontend/src/  React + TypeScript + Tailwind, tema escuro
docs/          especificação
```

## Dados e limites conhecidos

- **Cripto**: API pública da Binance (sem chave). **Ações e forex**: Yahoo Finance via `yfinance`
  (não oficial; serve ao MVP e está atrás de uma interface para ser trocado).
- Ouro spot (`XAUUSD`) não existe no Yahoo: os cálculos usam o futuro `GC=F`, enquanto o gráfico do TradingView mostra o spot da OANDA.
  Os dois diferem um pouco.
- O widget do TradingView é só exibição: o app não lê valores dele nem desenha níveis nele.
- O dado de 1 hora do Yahoo vai até ~730 dias; a avaliação do diário usa 1h quando possível e diário como reserva.
- O intervalo de confiança da inclinação assume amostras independentes e usa um único ativo: amostras pequenas aparecem como "sem dados".

## Segurança

Chaves (futuras: Anthropic, Telegram) vão em `.env` (modelo em `.env.example`), nunca no git.
