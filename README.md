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

## Status (v0.9)

| Pronto | Ainda não |
|---|---|
| **Scanner:** varredura do universo inteiro em segundo plano, setups editáveis em **D1 ou H4**, lista filtrável, falhas reportadas | Alertas por e-mail |
| Ficha do ativo: gráfico (widget do TradingView, abre sempre com o **Supertrend**), indicadores, saúde dos dados | |
| Inclinação probabilística (P(alta em N dias \| estado) com amostra, intervalo e base) | |
| Painel de correlação (só código): S&P 500 e DXY fixos + ~40 candidatos, alinhados às 16h de Nova York, parecer e gráficos | |
| Diário: registro, acompanhamento automático do resultado (alvo × invalidação × expirada), saída antecipada | |
| **Alertas de preço:** avulsos e níveis do plano do diário, detecção por máxima/mínima, notificação do Windows e **mensagem no Telegram** | |
| **Análise com IA (OpenRouter):** lentes por mercado, prompt fixo versionado, saída em JSON, citações conferidas por código, sem veredito global | |
| **Revisão do acerto:** por decisão, mercado, setup, bloco de código, lente de IA e respostas dos alertas, sempre com n e intervalo | |
| **Memória da IA:** pós-mortem com causa em lista fixa, casos parecidos (na ficha e, opcionalmente, na análise com IA) e alertas estatísticos só por código | |

### Scanner

- **Universo:** 518 ações (listas em `backend/app/scanner/data`, atualizáveis com `scripts/update_universes.py`), as ~60 criptos
  mais líquidas da Binance (volume 24h ≥ US$ 10 mi, sem stablecoins nem tokens alavancados) e 29 pares de forex.
- **Dados:** diário (~2 anos) e H4 (~1 ano), **só barras já fechadas**. Só baixa o que algum setup habilitado usa: sem setup H4 no
  mercado, o histórico de 1 hora nem é baixado. Ativos que falham aparecem no resultado ("2 falhas"; as de H4 levam "(H4)"), nunca em silêncio.
- **Timeframe do setup:** cada setup é D1 ou H4 ("Duplicar em H4" copia um setup para o outro timeframe). No H4, "barras" nas
  condições são barras de 4 horas e o volume é comparado com o mesmo horário do dia (a manhã de uma ação sempre tem mais volume
  que a tarde). A grade de 4 horas depende do mercado:
  - **Ações:** duas barras por pregão, 09:30–13:30 e 13:30–16:00 de Nova York (a segunda tem 2h30; o mesmo corte do TradingView).
  - **Forex e ouro:** blocos de 4 h a partir das 17:00 de Nova York (17, 21, 01, 05, 09, 13h). É a convenção do dia do forex; a sua
    corretora pode usar outra grade (por exemplo, relógio do servidor), e aí as barras diferem.
  - **Cripto:** a grade da Binance (00, 04, 08, 12, 16 e 20 UTC), que já vem em 4 horas.
  O Yahoo não entrega 4 horas: as barras são montadas a partir das de 1 hora, e uma barra só vale quando a última hora dela já existe
  (o Yahoo atrasa ouro e índices 10 a 15 minutos).
- **Setup** = condições obrigatórias (todas) + confirmações (mínimo configurável) + filtros de liquidez (só ações). Catálogo de
  ~20 condições (RSI, MACD, tendência, médias, volume, Bollinger, ATR, distância da máxima...). Condições de volume são
  ignoradas em forex.
- Os três setups iniciais são as regras do scanner antigo (que usava H4), sem score, e **existem nos dois timeframes**: D1 (o nome original) e
  H4 (o mesmo nome com "(H4)"), com as mesmas condições e filtros. Quem já tinha os três diários ganha as versões H4 uma única vez, só dos que
  ainda existem com o nome original; se você apagar um H4 de propósito, ele não volta. A varredura fica mais longa com o H4 ligado
  (~150 s em vez de ~95 s para o universo todo): desmarque os H4 em "Setups" se não quiser. **O backtest feito antes não achou vantagem sobre
  entradas aleatórias**: eles existem para você editar e para o diário medir.
- A primeira varredura real (22/10/2026) levou ~95 s e listou 172 achados em 171 ativos (29% do universo): setups largos listam
  muito. Aperte as condições ou use os filtros da lista. Com os três setups também em H4, a varredura levou ~150 s e o H4 listou 94
  ativos (16% do universo).
- Abrir um achado H4 leva à ficha com o gráfico do TradingView em 4 horas; **indicadores, probabilidade e correlação da ficha
  continuam diários**.

### Análise com IA (OpenRouter)

O botão **Analisar com IA** fica na ficha do ativo e roda uma "lente" por tema, cada uma em uma chamada separada e vendo só os
dados dela. Ações: macro, fundamentalista, indicadores, price action. Forex: macro e fundamentos, indicadores, price action. Cripto:
referência (BTC, risco, dólar), indicadores, price action. **Não há veredito global**: as lentes podem divergir, e a tela mostra isso.

- **A IA só interpreta.** Indicadores, níveis, correlações, macro e fundamentos são calculados por código e entregues num pacote
  JSON; a IA não busca nada nem faz contas. Calendário econômico, inflação, bancos centrais e notícias **não** entram: aparecem como lacuna.
- **Cada lente responde em JSON**: inclinação (para alta, para baixa, indistinta ou sem dados), confiança, resumo, evidências, o
  que faltou e o que mudaria a conclusão. As evidências citam um campo do pacote e um valor: o app **confere cada citação** e marca
  com ⚠ as que não existem ou não batem.
- **Prompt fixo e versionado** (v1): a versão e uma impressão digital dos textos ficam gravadas em cada análise, e a tela mostra o pacote
  enviado e os prompts. Mudar um texto exige criar a v2.
- **Configuração**: crie uma chave em <https://openrouter.ai/keys>, ponha saldo em <https://openrouter.ai/credits> e preencha
  `OPENROUTER_API_KEY` no `.env` (modelo em `AI_MODEL`, esforço de raciocínio em `AI_REASONING_EFFORT`, ver `.env.example`).
  **Reinicie o app** depois de editar o `.env`. A conta da OpenRouter é separada de qualquer assinatura Claude.
- **Custo**: vem da própria OpenRouter e aparece em cada análise. O padrão é `anthropic/claude-sonnet-5.5` com raciocínio `low`
  (o raciocínio é cobrado como saída). Para comparar com um modelo mais barato, troque `AI_MODEL` para `anthropic/claude-haiku-5.5`.
- **Privacidade**: por padrão só dados de mercado vão para a OpenRouter; nada do diário (teses, notas, decisões) é enviado. Há duas
  exceções, ambas opcionais e avisadas na tela: o **pós-mortem** (envia o caso, a tese e o motivo da saída que você escreveu) e a
  **memória na análise** (casos parecidos estruturados, sem texto livre). Ver "Memória da IA".
- O resumo das lentes vai junto quando você registra a decisão no diário.

### Memória da IA

A IA não aprende sozinha: o app lembra por ela, em três partes. A aba **Memória** reúne as duas primeiras e a ficha do ativo mostra a terceira.

- **Pós-mortem** (uma chamada paga por caso, só quando você pede; nunca automática): vale para tese **invalidada** e para
  **saída antecipada**. O pacote separa o que **já era visível no registro** (indicadores, probabilidade, price action,
  correlação, as lentes de IA da época, o quanto o movimento já estava esticado) do que **aconteceu depois** (o caminho do preço em
  múltiplos de R, o que veio depois de uma saída antecipada e a variação de dólar, juros, VIX e índices no período, tudo por código;
  só entram fechamentos das 16h de Nova York que já tinham acontecido, para não olhar o futuro). A IA escolhe **uma causa de uma
  lista fixa** (`causas-v1`): evento macro, referência divergiu, indicador deu ruído, invalidação ignorada, entrada tardia ou
  **sem causa identificável** (resposta normal e frequente, preferida a uma história plausível). Responde em JSON, marca o que era
  visível × o que só ficou claro depois e pode levantar até duas **hipóteses**, sempre rotuladas assim.
- **O código confere a resposta** e mostra os avisos ao lado dela: citação que não bate com o pacote, causa que não vale para a
  decisão (invalidação ignorada e entrada tardia só para quem entrou), "invalidação ignorada" sem saída registrada depois do toque,
  "evento macro" sem nenhuma referência se mover de forma notável, "entrada tardia" sem o preço ter andado a favor antes, respostas
  incoerentes. O pacote enviado fica gravado e pode ser aberto. Prompt e esquema são versionados (`pm-v1`, travados por hash).
- **Casos parecidos**: na ficha do ativo, o cartão "Memória do diário" lista as teses já resolvidas de estado parecido (mesmo ativo,
  mesmo mercado, setup em comum e cada bloco de código que aponta o mesmo lado), com **os motivos da semelhança** e o desfecho. O
  corte é de 3 pontos; com poucos registros, poucos casos passam.
- **Alertas estatísticos (só código)**: só aparecem diferenças **distinguíveis do acaso** entre partes do diário (setup, mercado,
  entrou × ficou de fora, saída antecipada, blocos e lentes): ao menos 10 teses resolvidas em cada lado e intervalo de 95% da
  diferença fora do zero, sempre com o n. A tela mostra quantas comparações foram testadas e quantos "distinguíveis" o acaso sozinho
  produziria (≈ 5%): é indício para olhar os casos, nunca regra. A IA só entra com hipóteses, que nunca viram alerta.
- **Na análise com IA** há a opção **"Usar a memória do diário"** (desligada por padrão): usa o prompt **v2** (a v1 mais uma regra
  sobre a memória; a v1 segue intacta) e entrega a cada lente os casos parecidos e as estatísticas. Cada lente vê, nos casos, só o que
  ela mesma disse na época. O que sai do computador é estruturado e sem texto livre: mercado, ativo, direção, mês, desfecho, prazo,
  motivos da semelhança, a resposta passada da própria lente e a causa do pós-mortem. **Não vão** tese, notas, motivo de saída,
  decisão nem preços. O pós-mortem, por outro lado, **envia a tese e o motivo da saída que você escreveu**, e a tela avisa antes.
- Custo: cada pós-mortem é uma chamada (o custo real fica gravado e o médio aparece na tela). Ainda não foi medido com um modelo real.

### Alertas de preço

- **Avulsos** (ativo, nível, direção, nota) ou **gerados pelo diário**: ao registrar uma tese, a invalidação e o alvo viram
  alertas (e a entrada, se você está só observando e ela está longe do preço atual). Quando um dos dois toca, o outro é
  cancelado; encerrar a tese, sair antes ou excluir o registro também cancela.
- **Detecção pela máxima e pela mínima** das barras de 1 minuto: um pavio que toca o nível dispara, mesmo se o fechamento
  ficou do outro lado. Cada alerta dispara uma vez.
- **Telegram** (opcional, além do toast; ver abaixo).
- **Notificação do Windows** (toast via PowerShell; clicar abre o app). Use "Testar notificação" na aba Alertas. O modo
  "Não incomodar" do Windows manda o aviso direto para a central de notificações.
- Ao disparar, o app pergunta o que você fez (entrei / ignorei / observando); o contador de pendentes aparece na aba.
- **Só vigia com o app aberto** (o servidor). Ao ligar, confere o que aconteceu enquanto esteve desligado.
- **O atraso do alerta é o atraso do dado.** Medido em 22/10/2026: cripto (Binance) e ações dos EUA (Yahoo) ~1 min; forex 1 a 2 min;
  ouro (futuro), DXY e índices europeus 10 a 15 min. Variáveis: `ALERT_POLL_SECONDS` (padrão 60), `ALERTS_WATCHER=0` para desligar.

### Revisão do acerto

Aba **Revisão**: mede o que o diário e os alertas já registraram. **Acerto da tese** = alvo ÷ (alvo + invalidada); expiradas e
abertas ficam fora da taxa, mas aparecem. Toda taxa mostra o n e o intervalo de 95% (a barra azul); amostra com menos de 10
resolvidas aparece esmaecida e abaixo de 30 vem com aviso. Não há score nem veredito.

- **Por tipo de decisão:** a taxa da tese em cada uma (entrei, não entrei, observando) e a "decisão certa" (entrar e a tese bater o
  alvo, ou ficar de fora e ela ser invalidada). Compara as teses em que você entrou com as que deixou de fora e mostra o que a
  tese fez depois das saídas antecipadas.
- **Por mercado** e **por setup.**
- **Por bloco de código** (probabilidade, tendência, MACD, price action, correlação com S&P 500 e com DXY) e **por lente de IA:**
  a pergunta é se a tese bateu o alvo mais vezes quando o bloco **concordava** com ela do que quando **discordava**. Se o bloco não
  soubesse nada, as duas taxas seriam iguais; a diferença vem com intervalo e só é chamada de "distinguível" com ao menos 10
  resolvidas em cada lado. As regras de leitura de cada bloco (`blocos-v1`) aparecem na tela.
- **Respostas dos alertas:** quantos disparos, o que você respondeu e, nos alertas de entrada, o que a tese fez depois.
- Registros anteriores a esta versão não guardaram price action nem correlação (ficam fora desses blocos). O botão **Reavaliar
  teses abertas** atualiza os desfechos antes de olhar a revisão.
- **Cuidado com a leitura:** são dezenas de comparações, então algumas vão parecer distinguíveis só por acaso; só vale o que se
  repete em registros novos. Boa decisão com resultado ruim existe, e o quadro não separa uma da outra.

### Alertas no Telegram

Cada alerta que dispara vira também uma mensagem num **bot que você cria** (o app não tem bot próprio e só envia: não lê nem responde ao que você escrever).

1. No Telegram, abra o **@BotFather**, envie `/newbot` e siga os passos: ele devolve um **token**.
2. Cole no `.env` como `TELEGRAM_BOT_TOKEN=...` e **reinicie o app**.
3. Mande qualquer mensagem ao seu bot (por exemplo `/start`).
4. Na aba **Alertas → Alertas no Telegram**, clique em "Procurar conversas" e vincule **a sua** (o app lista as conversas em vez de pegar a mais
   recente: qualquer pessoa que descubra o bot pode escrever a ele, e só a conversa vinculada recebe os alertas). Ele manda uma mensagem de
   confirmação nessa conversa. Use "Enviar mensagem de teste" para conferir. Alternativa: `TELEGRAM_CHAT_ID` no `.env`.

- **A mensagem** traz o tipo (alerta de preço, entrada, invalidação ou alvo), o ativo, o nível, o extremo tocado e o horário da barra, a nota e um
  lembrete para responder no app. Se o app só percebeu o toque bem depois (estava desligado ou o dado atrasou), diz isso.
- **Privacidade:** a mensagem passa pelos servidores do Telegram (não é ponta a ponta). A nota dos alertas do plano começa com um trecho da tese:
  desmarque "Incluir a nota do alerta" se não quiser isso fora do computador.
- **O token** fica só no `.env`: nunca vai ao navegador, ao banco, ao git nem a mensagens de erro (o app o apaga de qualquer erro, porque a
  URL da API do Telegram o carrega). Só o id da conversa vinculada fica no banco.
- **Falhas:** o toast do Windows e o registro no app seguem mesmo se o Telegram falhar. A mensagem que falhou é reenviada com espera crescente
  (1, 2, 5, 15 e 60 min; até 6 tentativas, só para alertas das últimas 24 h) e vai marcada como "Reenviada". Cada alerta mostra se o Telegram
  saiu ou falhou. Ligar o Telegram depois não reenvia alertas antigos.
- Como o resto da vigilância, **só funciona com o app aberto**.

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
  ai/           análise com IA: pacote de dados, prompts versionados, cliente da OpenRouter, conferência das citações
  alerts/       alertas de preço: regra de disparo, vigilância em segundo plano, notificação do Windows
  scanner/      universo, catálogo de condições, setups, varredura em segundo plano
  correlation/  universo de candidatos, alinhamento 16h NY, motor de correlação
  providers/    fontes de preço atrás de uma interface comum (Yahoo, Binance) + símbolos
  analysis/     indicadores (RSI/ATR de Wilder, MACD, Bollinger) e inclinação probabilística
  journal/      avaliação do plano de uma tese (alvo × invalidação × horizonte, em R)
  review/       revisão do acerto: regras de leitura dos blocos e estatística por grupo
  memory/       memória da IA: causas fixas, caminho do preço, pós-mortem, casos parecidos, alertas estatísticos
  routes/       API (/api/scanner, /api/asset, /api/correlation, /api/journal, /api/alerts, /api/ai, /api/review, /api/memory, /api/telegram)
backend/scripts/ atualização das listas de ações
frontend/src/   React + TypeScript + Tailwind, tema escuro
docs/           especificação
```

## Dados e limites conhecidos

- **Cripto**: API pública da Binance (sem chave). **Ações e forex**: Yahoo Finance via `yfinance`
  (não oficial; serve ao MVP e está atrás de uma interface para ser trocado).
- Ouro spot (`XAUUSD`) não existe no Yahoo: os cálculos usam o futuro `GC=F`, enquanto o gráfico do TradingView mostra o spot da OANDA.
  Os dois diferem um pouco.
- O widget do TradingView é só exibição: o app não lê valores dele nem desenha níveis nele. O gráfico abre sempre com o **Supertrend** do
  TradingView (ATR 10, fator 3) por padrão; ele é só visual, os cálculos do app (blocos, probabilidade, scanner) não o usam. Para trocar ou
  somar indicadores, edite `DEFAULT_STUDIES` em `frontend/src/components/TradingViewChart.tsx`.
- Barras diárias de forex podem ficar em formação até ~17h de Nova York; o corte do scanner é o último 16:00 de Nova York.
- O dado de 1 hora do Yahoo vai até ~730 dias; a avaliação do diário usa 1h quando possível e diário como reserva. O H4 de ações e
  forex usa 1 ano dele.
- O intervalo de confiança da inclinação assume amostras independentes e usa um único ativo: amostras pequenas aparecem como "sem dados".

## Segurança

Chaves (a da OpenRouter e o token do bot do Telegram) vão em `.env` (modelo em `.env.example`), nunca no git.
