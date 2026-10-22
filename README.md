# Trade Journal

App web local para **varrer o mercado atrás dos seus setups, analisar os ativos encontrados e registrar as próprias
decisões**, para descobrir se "setup + decisão humana" é viável. Nada é automático: o app nunca opera. A pergunta central
não é lucro, é **acerto da tese e qualidade de decisão**.

> Ferramenta de apoio à decisão do próprio usuário; não é recomendação de investimento.
> Probabilidades mostradas são frequências históricas, não garantias.

Desenho completo: [docs/ESPECIFICACAO.md](docs/ESPECIFICACAO.md).

## Fluxo (funil)

1. **Scanner** (aba inicial): varre ~600 ativos (S&P 500 + Nasdaq-100, as cripto mais líquidas da Binance, forex majors/minors
   e ouro) atrás dos seus **setups** e lista o que encontrou.
2. **Ativo**: abrir um achado leva à ficha completa (gráfico, indicadores, inclinação probabilística, painel de correlação).
3. **Diário**: registrar a decisão (entrei / não entrei / observando) com tese, invalidação e alvo; o app acompanha o resultado.

## Status (v0.4)

| Pronto | Ainda não |
|---|---|
| **Scanner:** varredura do universo inteiro em segundo plano, setups editáveis, lista filtrável, falhas reportadas | Botão de IA (lentes) e memória/pós-mortem |
| Ficha do ativo: gráfico (widget do TradingView), indicadores, saúde dos dados | Alertas por Telegram ou e-mail |
| Inclinação probabilística (P(alta em N dias \| estado) com amostra, intervalo e base) | Revisão do acerto por bloco e por lente |
| Painel de correlação (só código): S&P 500 e DXY fixos + ~40 candidatos, alinhados às 16h de Nova York, parecer e gráficos | Timeframe H4 nos setups |
| Diário: registro, acompanhamento automático do resultado (alvo × invalidação × expirada), saída antecipada | |
| **Alertas de preço:** avulsos e níveis do plano do diário, detecção por máxima/mínima, notificação do Windows | |

### Scanner

- **Universo:** 518 ações (listas em `backend/app/scanner/data`, atualizáveis com `scripts/update_universes.py`), as ~60 criptos
  mais líquidas da Binance (volume 24h ≥ US$ 10 mi, sem stablecoins nem tokens alavancados) e 29 pares de forex.
- **Dados:** diário, ~2 anos, **só barras já fechadas**. Ativos que falham aparecem no resultado ("2 falhas"), nunca em silêncio.
- **Setup** = condições obrigatórias (todas) + confirmações (mínimo configurável) + filtros de liquidez (só ações). Catálogo de
  ~20 condições (RSI, MACD, tendência, médias, volume, Bollinger, ATR, distância da máxima...). Condições de volume são
  ignoradas em forex.
- Os três setups iniciais são as regras do scanner antigo, sem score e em timeframe diário. **O backtest feito antes não achou
  vantagem sobre entradas aleatórias**: eles existem para você editar e para o diário medir.
- A primeira varredura real (22/10/2026) levou ~95 s e listou 172 achados em 171 ativos (29% do universo): setups largos listam
  muito. Aperte as condições ou use os filtros da lista.

### Alertas de preço

- **Avulsos** (ativo, nível, direção, nota) ou **gerados pelo diário**: ao registrar uma tese, a invalidação e o alvo viram
  alertas (e a entrada, se você está só observando e ela está longe do preço atual). Quando um dos dois toca, o outro é
  cancelado; encerrar a tese, sair antes ou excluir o registro também cancela.
- **Detecção pela máxima e pela mínima** das barras de 1 minuto: um pavio que toca o nível dispara, mesmo se o fechamento
  ficou do outro lado. Cada alerta dispara uma vez.
- **Notificação do Windows** (toast via PowerShell; clicar abre o app). Use "Testar notificação" na aba Alertas. O modo
  "Não incomodar" do Windows manda o aviso direto para a central de notificações.
- Ao disparar, o app pergunta o que você fez (entrei / ignorei / observando); o contador de pendentes aparece na aba.
- **Só vigia com o app aberto** (o servidor). Ao ligar, confere o que aconteceu enquanto esteve desligado.
- **O atraso do alerta é o atraso do dado.** Medido em 22/10/2026: cripto (Binance) e ações dos EUA (Yahoo) ~1 min; forex 1 a 2 min;
  ouro (futuro), DXY e índices europeus 10 a 15 min. Variáveis: `ALERT_POLL_SECONDS` (padrão 60), `ALERTS_WATCHER=0` para desligar.

### Painel de correlação

Na primeira vez, clique em **Atualizar universo** (30 s a 2 min): ele baixa os candidatos (índices, juros, VIX, commodities,
cripto, forex, ETFs de setor) e guarda no SQLite local. Cada ativo é amostrado a partir de dados de 1 hora na última barra
que fecha às 16h de Nova York, para que forex, cripto e bolsas sejam comparados no mesmo instante. Relações mecânicas (par de
forex com moeda em comum, DXY × par com USD, ação × ETF do próprio setor) ficam marcadas e escondidas por padrão. A janela é
de ~2 anos (limite do dado de 1 hora do Yahoo).

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

Abra <http://127.0.0.1:8765>. Os dados (diário, setups, varreduras) ficam em `data/journal.db` (fora do git; faça backup).
Se a porta 8765 estiver ocupada por uma execução anterior, encerre o processo antes de iniciar de novo.

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
  alerts/       alertas de preço: regra de disparo, vigilância em segundo plano, notificação do Windows
  scanner/      universo, catálogo de condições, setups, varredura em segundo plano
  correlation/  universo de candidatos, alinhamento 16h NY, motor de correlação
  providers/    fontes de preço atrás de uma interface comum (Yahoo, Binance) + símbolos
  analysis/     indicadores (RSI/ATR de Wilder, MACD, Bollinger) e inclinação probabilística
  journal/      avaliação do plano de uma tese (alvo × invalidação × horizonte, em R)
  routes/       API (/api/scanner, /api/asset, /api/correlation, /api/journal, /api/alerts)
backend/scripts/ atualização das listas de ações
frontend/src/   React + TypeScript + Tailwind, tema escuro
docs/           especificação
```

## Dados e limites conhecidos

- **Cripto**: API pública da Binance (sem chave). **Ações e forex**: Yahoo Finance via `yfinance`
  (não oficial; serve ao MVP e está atrás de uma interface para ser trocado).
- Ouro spot (`XAUUSD`) não existe no Yahoo: os cálculos usam o futuro `GC=F`, enquanto o gráfico do TradingView mostra o spot da OANDA.
  Os dois diferem um pouco.
- O widget do TradingView é só exibição: o app não lê valores dele nem desenha níveis nele.
- Barras diárias de forex podem ficar em formação até ~17h de Nova York; o corte do scanner é o último 16:00 de Nova York.
- O dado de 1 hora do Yahoo vai até ~730 dias; a avaliação do diário usa 1h quando possível e diário como reserva.
- O intervalo de confiança da inclinação assume amostras independentes e usa um único ativo: amostras pequenas aparecem como "sem dados".

## Segurança

Chaves (futuras: Anthropic, Telegram) vão em `.env` (modelo em `.env.example`), nunca no git.
