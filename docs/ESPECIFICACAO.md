# Especificação — App de análise e diário de decisões (cripto, ações, forex)

Status: rascunho v0.1 — 2026-10-22. Nada implementado ainda.
Substitui, como direção, os scanners antigos desta pasta (ver "Defeitos do scanner antigo").

## 1. Objetivo

Ajudar **uma pessoa** a analisar oportunidades diárias em três mercados e **registrar as próprias decisões**
para descobrir se "setup + decisão humana" é viável. Nada é automático: o app nunca opera.

A pergunta que o app responde ao longo do tempo **não é lucro**, é acerto e qualidade de decisão:
a tese se confirmou? Sair antes foi bom? Qual bloco de análise (ou a IA) acertou mais?

## 2. Princípios

1. **Decisão humana.** O app apresenta análises e divergências; não emite ordem.
2. **Sem veredito global e sem score único.** (O score do scanner antigo não previu nada — ver seção 14.)
   Cada bloco fala por si; o app mostra a divergência entre eles.
3. **Código calcula, IA interpreta.** A IA nunca busca dados nem calcula indicador; só lê o pacote de dados que o código montou.
4. **"Sem dados" é resposta válida**, para código e para IA. Nunca inventar.
5. **Tudo é gravado** (dados enviados, respostas, decisão, resultado) para auditoria e revisão.
6. **Funil**: cada etapa reduz o universo; o que custa dinheiro (IA) fica no fim.
7. **Probabilidade, não sinal.** Cada bloco informa a inclinação provável dado o estado atual, com a frequência histórica,
   o tamanho da amostra e a base do ativo — nunca uma ordem de compra ou venda.

## 3. Mercados e universo

| Mercado | Universo inicial |
|---|---|
| Ações | S&P 500 e Nasdaq |
| Cripto | pares mais líquidos (ex.: top por volume na Binance) |
| Forex | majors e minors (inclui ouro, ver seção 12) |

Lista de ativos por mercado: **a definir pelo usuário** (editável no app).

## 4. Funil (fluxo do app)

1. **Universo** → varredura por código, sem IA.
2. **Setup** → o usuário define o setup (conjunto de condições). O app separa os ativos que o atendem
   e mostra **quais condições bateram** (sem score).
3. **Página do ativo** → ao abrir um ativo da lista vem tudo junto: gráfico, indicadores, price action,
   painel de correlação com parecer, viés por bloco, histórico do usuário com aquele ativo.
4. **Botão "Analisar com IA"** → lentes interpretando o pacote (seção 7). Único ponto com custo.
5. **Diário** → registra a decisão e também o funil (listado / aberto / entrado / ignorado),
   para medir se o setup seleciona bem.

Qualquer ativo também pode ser aberto manualmente, fora do funil.

## 5. Análise por código (botão "Analisar", sem IA)

### 5.1 Blocos
- **Indicadores**: RSI (Wilder, para bater com o TradingView), MACD, médias móveis, ATR, Bollinger. Volume só em ações e cripto (forex não tem volume centralizado).
- **Price action objetivo**: estrutura de topos/fundos, níveis, distância a suporte/resistência em ATR.
- **Correlação / referência** (seção 6), com parecer por código.
- **Saúde dos dados**: fonte, hora da última barra, atraso (seção 12).

### 5.2 Inclinação probabilística por bloco (decisão registrada)
Não é sinal de compra/venda. Cada bloco de código descreve o **estado atual** e informa, a partir do histórico,
**quão provável é cada lado** naquele estado:
- Estado = poucas faixas grosseiras (ex.: RSI em 3 zonas × MACD acima/abaixo × tendência sim/não), para ter amostra.
- Saída: `P(alta em N dias | estado)`, **n** (ocorrências sem sobreposição), intervalo de confiança de 95%,
  a **base do próprio ativo** (`P(alta em N dias)` sem condição) e a diferença (lift) em pontos percentuais.
- Rótulo: `inclinação para alta | para baixa | indistinta | sem dados`. Só é "alta/baixa" quando o intervalo exclui a base;
  com n < 30 (ajustável) é `sem dados`. A maioria dos estados deve cair em `indistinta` — isso é informação, não falha.
- Usa só dados anteriores à data (sem olhar o futuro). N = horizonte do plano (ex.: 10 dias), configurável.
- Amostra: histórico do próprio ativo; se n for pequeno, pode usar o histórico agrupado do mercado, sempre rotulado como tal.
- Intervalos por bootstrap por dia (ativos no mesmo dia andam juntos; intervalo que assume independência fica estreito demais).
- Mostra as regras do estado (transparente) e **não agrega** em veredito único: os blocos aparecem lado a lado.
- Custo zero, instantâneo, determinístico, disponível para toda a lista do funil antes de gastar com IA.
- A inclinação de cada bloco e a postura de cada lente de IA são gravadas e pontuadas contra o resultado;
  depois de casos suficientes, o diário mostra qual vale manter (decidir pelos dados).
- Cuidado: testar muitos estados gera falsos positivos; manter o conjunto de estados pequeno e fixo e validar no diário antes de confiar.

## 6. Painel de correlação (só código)

Mostra o ativo com seus correlacionados. S&P 500 e DXY ficam sempre fixados; o app acrescenta os descobertos
entre ~46 candidatos editáveis (índices S&P 500, Nasdaq 100, Russell 2000, DAX, FTSE, Nikkei, Hang Seng;
DXY, juros 5a/10a, VIX, TLT, HYG; ouro, prata, petróleo, cobre, gás; BTC, ETH, SOL; ~13 pares de forex; 9 ETFs de setor).

Regras:
- **Alinhar todos os ativos no mesmo instante (16:00 de Nova York)** a partir de dados de 1 hora.
  Sem isso o forex falseia: EURUSD × DXY deu −0,10 no diário do Yahoo e −0,98 alinhado.
- Usar **retornos**, não preços (juros em variação de pontos).
- Janelas de 20, 60 e 250 dias; mostrar também a faixa histórica da correlação de 60 dias.
- **Estável** = mesmo sinal em ≥ 80% das janelas de 60 dias, correlação semanal concordando e |corr| ≥ 0,30 (ajustável).
  Quando não for estável, o app diz "sem relação estável" em vez de forçar o par.
- **Rotular e esconder por padrão** relações mecânicas: pares com moeda em comum, DXY × pares com USD, ação × seu próprio setor/índice.
- **Agrupar por fator** (risco, dólar/juros, commodities, cripto, forex, setores) para não listar dez versões de "risco liga/desliga".
- Mostrar se o ativo **concorda ou diverge** dos correlacionados nos últimos dias.

Parecer por código (exemplo medido, NVDA): regressão do ativo contra as referências fixadas; compara o retorno real
dos últimos 20 dias com o esperado; classifica |z| < 1 normal, 1–2 divergência relevante, > 2 forte.
O modelo inclui a tendência média do ativo no período.

Saída: gráficos próprios (linhas rebaseadas em 100, correlação móvel, dispersão com a reta) + texto gerado por regras.

Implementação (v0.2):
- O universo (43 instrumentos do Yahoo) é baixado sob demanda pelo botão "Atualizar universo" (~30 s a 2 min) e guardado em
  SQLite; passa a "desatualizado" depois de 20 h.
- Fixadas: S&P 500 e DXY. Se a relação com uma fixa for mecânica (ex.: EURUSD × DXY), ela sai do parecer.
- Ação × ETF do próprio setor é detectada pelo setor/indústria do Yahoo (`info`); se a consulta falhar, o ETF aparece normalmente.
- O parecer não compara "esperado × real" quando os referenciais explicam menos de 5% do ativo (R²).
- "Descolamento de 20 dias" só é mostrado para relações estáveis: |z| < 1 normal; 1–2 divergência relevante; > 2 forte.
- Validado contra uma varredura independente feita antes: NVDA × S&P +0,70 e × DXY +0,04; ouro × DXY −0,42 (estável em 99%
  das janelas); EURUSD × DXY −0,98 (mecânica); parecer do NVDA idêntico (−3,2 pp, z = −0,60).

## 7. Análise com IA (botão separado)

- **Lentes por mercado**, cada uma em chamada separada recebendo **só a sua fatia dos dados**:
  - Ações: macro, fundamentalista, indicadores, price action.
  - Forex: macro/fundamental (política monetária, juros, calendário) juntos, indicadores (sem volume), price action.
  - Cripto: indicadores, price action e referência (BTC / Nasdaq / VIX); **sem lente fundamentalista**.
- Cada lente devolve JSON curto: inclinação (`para alta | para baixa | indistinta | sem dados`), confiança, evidências **citadas do pacote**,
  o que falta, o que mudaria a conclusão. **Sem veredito final.**
- **Prompt fixo por mercado e versionado**; a versão fica gravada em cada análise. O prompt só muda por decisão do usuário.
- A IA não navega na web e não calcula. Notícias, se usadas, entram como manchetes buscadas pelo código.
- O pacote inclui a saúde dos dados (para a IA não tratar dado velho como atual).
- Modelo: testar Sonnet 5.5 e Haiku 5.5 nos mesmos casos do diário e escolher.
- Custo estimado (premissas: ~9 mil tokens de entrada e ~2,4 mil de saída por clique, preços da tabela da Anthropic
  em 2026-10-06): ≈ US$ 0,04 com Sonnet 5.5; ≈ US$ 0,002 com Haiku 5.5. Raciocínio da IA conta como saída: usar esforço baixo/médio.
  Confirmar com medição real.

## 8. Diário e medição de acerto

Registro por ativo/decisão: decisão (entrei / não entrei / observando), tese, invalidação, alvo, horizonte,
snapshot completo (dados + vieses dos blocos + respostas das lentes + versão do prompt).

**Acerto da tese (sem falar de lucro):** alvo atingido antes da invalidação dentro do horizonte = acerto;
invalidação primeiro = erro; expirou = neutro. Medido em R (múltiplos do risco), não em dinheiro.

- **Saída antecipada**: registra o motivo e continua acompanhando o preço, mostrando o que teria acontecido mantendo o plano.
- **Ignorados** (setups listados que o usuário não tomou) também são acompanhados.
- **Revisão**: acerto por mercado; por bloco de código e por lente de IA (quando disse X, quanto acertou?);
  quando o usuário discordou de um bloco, quem estava certo; saída antecipada vs manter.

## 9. Memória da IA (fase posterior; a gravação começa no dia 1)

A IA não aprende sozinha; o app lembra e devolve contexto:
1. Registro de tudo (seção 8).
2. **Pós-mortem** quando a tese falha ou há saída antecipada: chamada com o pacote original, respostas das lentes e o caminho do preço depois;
   causa numa lista fixa (evento macro, referência divergiu, indicador deu ruído, invalidação ignorada, entrada tardia, sem causa identificável),
   separando o que era visível na época do que só ficou claro depois.
3. **Recuperação**: nas análises seguintes entram 3–5 casos semelhantes e estatísticas.
4. **Alertas estatísticos calculados por código**, sempre com o número de casos. A IA só pode sugerir hipótese, marcada como hipótese.

Limites conhecidos: viés retrospectivo e histórias plausíveis (daí a lista fixa e o "sem causa"); poucos casos = indício, não regra
(pensar em dezenas); o prompt só muda quando o usuário revisar e subir nova versão.

## 10. Alertas de preço

- Alerta avulso: ativo, preço, direção (cruzar acima/abaixo), nota.
- Os níveis do plano no diário (entrada, invalidação, alvo) viram alertas automaticamente.
- Ao disparar: grava hora e preço e pergunta o que o usuário fez (entrei / ignorei).
- Detecção por máxima/mínima do intervalo, não só pelo último preço.
- **O atraso do alerta é o atraso do dado.** Para preço exato é preciso fonte em tempo real.
- Só dispara com o app ligado. Notificação no Windows; opcional: bot do Telegram (token criado pelo usuário).

## 11. Gráficos

- Gráfico de preço: **widget do TradingView embutido por iframe** (gratuito, hospedado por eles, dados deles).
  Limites: só exibição (o código não lê os valores nem desenha níveis do usuário nele); atraso varia por mercado
  (não confirmado quais são tempo real no plano gratuito); termos de atribuição não confirmados; o preço do widget pode diferir um pouco da nossa fonte.
- Gráficos próprios só para o painel de correlação.
- Mapear o símbolo de cada ativo com o prefixo de bolsa correto (o scanner antigo fixava `NASDAQ:`).

## 12. Dados e fontes

Medido em 2026-10-22 no Yahoo (`yfinance`): forex e cripto ≈ 1 min de atraso; DXY e ouro futuro ≈ 11 min; DAX ≈ 16 min;
ações/S&P: fechamento do dia anterior (mercado fechado no momento do teste; atraso intradiário não medido).
BTC Yahoo vs Binance: −0,12%. Para swing em D1/H4 o atraso não pesa; o problema é a fragilidade da fonte
(não oficial; ouro spot `XAUUSD=X` não existe; tickers mortos; dado de 1 hora limitado a 730 dias; Stooq bloqueou consulta automática).

Estratégia: **camada de fontes trocável** + exibição de fonte/hora/atraso em cada análise.

| Mercado | Fonte proposta | Observações (a confirmar antes de assinar) |
|---|---|---|
| Cripto | Binance pública | testada: funciona sem chave |
| Ações/ETFs | Alpaca (gratuito) | só bolsa IEX (volume subestimado); 200 chamadas/min; histórico desde 2016; docs divergem na janela recente. Alternativa: Massive (ex-Polygon) gratuito = 5 chamadas/min, fim de dia, 2 anos; atraso 15 min a partir de ~US$ 29/mês |
| Forex | OANDA (conta prática) ou feed da corretora do usuário | candles desde 2005, 5000 por requisição; disponibilidade por país e ouro não confirmados. Alternativa: Twelve Data (8 créditos/min, 800/dia no Basic; classes cobertas não confirmadas) |
| Referências (DXY, VIX, juros, índices, commodities) | Yahoo (reserva) ou ETFs substitutos (UUP, SPY, QQQ, TLT, GLD) | sem fonte gratuita oficial encontrada; testar a fidelidade dos ETFs |

Ouro: spot não vem do Yahoo; usar futuro `GC=F` como substituto no MVP.

## 13. Técnica

- Backend: Python (FastAPI) + SQLite.
- Frontend: React + TypeScript (Vite), **tema escuro como padrão**; shadcn/ui (Tailwind) para componentes;
  TanStack Table/Query para tabelas e dados; Apache ECharts para os gráficos próprios (inclui heatmap de correlação).
  O widget do TradingView aceita tema escuro (confirmar na documentação).
- Após o build, o FastAPI serve os arquivos estáticos: um processo, uma porta, um comando para rodar (Node só para desenvolver/compilar).
- Empacotar como desktop depois, se quiser.
- **Sem container no MVP.** Ambiente com versões travadas (venv + arquivo de dependências).
  Código pronto para container: configuração por variáveis de ambiente, dados numa pasta só, sem caminhos fixos.
  Container num servidor passa a compensar se o usuário quiser alertas 24h.
- Ao abrir, o app recalcula o que ficou pendente (resultados de setups em aberto) a partir do histórico.
- Chaves de API em arquivo `.env` fora do controle de versão.

## 14. Evidências medidas nesta sessão

**Scanner antigo (`advanced_swing_scanner.py`)**, backtest com entrada na abertura seguinte, stop 1,5×ATR, alvo 3×ATR, 10 dias, custo 0,1%:

| Teste | Entrada aleatória | Scanner (score ≥ 60) |
|---|---|---|
| Regras exatas (H4), 21 meses | +0,049 R | +0,008 R (IC95 −0,06 a +0,08) |
| Variante diária, 10 anos | +0,084 R | +0,079 R (IC95 +0,05 a +0,11) |

Conclusão: sem vantagem sobre entrada aleatória; o score não ordena resultados; acerto 43–46% (a documentação antiga alegava 68–75% sem base).
Limites: H4 cobre 21 meses e um regime; universo de sobreviventes; variante diária não é idêntica.

**Correlações** (~2 anos, alinhadas às 16h NY; uma janela e um regime só):

| Ativo | Referências estáveis | DXY |
|---|---|---|
| Ouro | prata +0,78, AUDUSD +0,45, cobre +0,43 | −0,42 (estável em 99% das janelas) |
| BTC / SOL | ETH/SOL/BTC ≈ +0,8; Nasdaq +0,46 / Russell +0,45; VIX −0,41 | −0,08 / −0,10 |
| NVDA / JPM | S&P/Russell, setores, VIX −0,54 a −0,59 | ≈ 0, sinal muda |
| EURUSD / USDJPY | ouro +0,39 e juro 5a −0,36 / juros +0,43 a +0,47 | mecânica (−0,98 / +0,73) |
| AUDNZD | nenhuma estável | +0,25 |
| NVDA × S&P 500 | +0,70 (beta 1,9; mesmo sinal em 100% das janelas) | NVDA × DXY +0,04, sem estabilidade |

Premissas que **não** se sustentaram nos dados: "ouro cai quando o DAX sobe" (ouro × DAX +0,10, sinal muda por ano);
"cripto contra o DAX" (BTC × DAX +0,17, positiva).

**Estado → probabilidade (scanner antigo, 10 dias, 1 posição por ativo por janela):** a base de P(alta em 10 dias) foi
55,0% (diário, 10 anos) e 54,0% (H4, 21 meses). Os estados do scanner antigo ficaram praticamente iguais à base: setup válido
55,3% (+0,3 pp) no diário e 52,1% (−1,8 pp) no H4; tendência sozinha, MACD acima/abaixo do sinal e os três tipos de RSI
ficaram a ±1–3 pp. Três das 16 comparações saíram "distinguíveis" (todas abaixo da base; ex.: Oversold Recovery no diário,
−5,8 pp, n = 604), mas esses intervalos assumem observações independentes e ativos no mesmo dia andam juntos, então os intervalos
reais são mais largos — não tratar como evidência. Consequência para o desenho: mostrar sempre a base do ativo; "indistinta" será o resultado mais comum.

## 15. Defeitos do scanner antigo (não carregar para o app)

1. `resample('4H')` quebra no pandas atual e o erro é engolido (scanner responde "nenhum setup").
2. `swing_scanner_fast.py` chama `stock.download()`, que não existe em `yf.Ticker`.
3. RSI com média simples em vez de Wilder: difere do TradingView em média 6–7 pontos (picos > 30).
4. Lista com duplicatas, nomes que não são tickers (D-Wave, Rigetti, Honeywell, PsiQuantum, PSIQ, QCI), tickers mortos (MRO, SIVB, SQ) e ETFs alavancados.
5. Link do TradingView fixa `NASDAQ:` para ações da NYSE.
6. `risk_reward_1` é sempre 2,0 (alvo calculado a partir do stop); o README manda evitar earnings, mas nada checa.

## 16. Fases de construção

1. Ficha do ativo (iframe + dados + indicadores + painel de correlação + viés por bloco) e diário com acompanhamento automático de resultado.
2. Botão de IA com as lentes.
3. Radar/funil diário com setups definidos pelo usuário.
4. Painel de revisão (acerto por bloco/lente) e alertas de preço.
5. Memória: pós-mortem, recuperação e alertas estatísticos (depende de casos fechados).

## 17. Em aberto

- Corretora de forex do usuário (define a fonte de forex e o ouro).
- Lista de ativos de cada mercado.
- Definição dos setups, dos estados de cada bloco e do horizonte N usados na probabilidade (defaults a combinar).
- Limites e termos das fontes (seção 12) e do widget TradingView (seção 11).
- Canal de notificação dos alertas (Windows, Telegram).

Nota: ferramenta de apoio à decisão do próprio usuário; não é recomendação de investimento.
