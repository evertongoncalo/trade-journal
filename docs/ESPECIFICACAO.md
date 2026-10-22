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

Implementação (v0.3): o scanner é a porta de entrada do app (aba inicial).
- Universo: S&P 500 + Nasdaq-100 (518 ações; listas em `app/scanner/data`, atualizáveis por `scripts/update_universes.py`),
  as ~60 criptos mais líquidas da Binance (volume 24h ≥ US$ 10 mi, sem stablecoins nem tokens alavancados) e 29 pares de forex
  (7 majors, 21 minors e o ouro).
- Dados: diário, ~2 anos, só barras já fechadas (corte no último 16:00 de Nova York; cripto pelo `closeTime` da Binance).
  Ativos que falham são listados no resultado, nunca engolidos (defeito do scanner antigo).
- Setup = condições obrigatórias (todas) + confirmações (mínimo configurável) + filtros de liquidez (só ações). Catálogo de ~20
  condições; as de volume são ignoradas em forex.
- Os 3 setups iniciais traduzem o scanner antigo sem score e em timeframe diário (o antigo usava RSI/MACD em H4; o H4 veio na
  v0.7, ver abaixo). Sem evidência de que superem o acaso (seção 14).
- Primeira varredura real (2026-10-22): 601 ativos em 95 s; 172 achados em 171 ativos (29% do universo). Setups largos listam muito.
- Resultados ficam no SQLite (varredura + achados). Abrir um achado registra a abertura e leva o nome do setup ao diário.

Implementação (v0.7): **timeframe H4 nos setups** (cada setup é D1 ou H4; coluna `timeframe` em `setups` e `scan_hits`, com migração
automática de bancos antigos, que ficam D1).
- Dados: o Yahoo não tem 4 horas, então as barras H4 de ações e forex são montadas das de 1 hora (~1 ano). Cripto usa as barras de
  4 horas da própria Binance (1000 barras, ~167 dias). Medido em 2026-10-22: 40 ações em 1 hora levam ~6 s por lote (o universo
  todo, ~80 s); a varredura D1 + H4 completa levou 152 s para 600 ativos, 597 avaliados e 4 falhas (tickers com histórico curto).
- Grades (decisão, ver `scanner/bars.py`): ações em duas barras por pregão, 09:30–13:30 e 13:30–16:00 NY (o corte do TradingView);
  forex e ouro em blocos de 4 h ancorados às 17:00 NY, que é o início do dia do forex (a grade da corretora do usuário pode diferir;
  pendência já registrada na seção 17); cripto na grade UTC da Binance. A grade do forex segue o relógio de Nova York, então desloca 1 h
  em UTC na troca de horário; o mercado está fechado nessas trocas (domingo), por isso não gera barra torta.
- **Só barras fechadas**: a última barra só vale se o relógio já passou do fim dela e se existe a barra de 1 hora que cobre o
  último trecho (o Yahoo atrasa ouro e índices 10 a 15 minutos; sem essa checagem nasceria uma barra sem a última hora). Teste de
  mutação: desligar a regra derruba os testes.
- Volume em H4 é comparado com as barras do MESMO horário do dia (média de 20): sem isso a barra da manhã de uma ação pareceria sempre
  "volume alto" e a da tarde sempre "baixo". O filtro de liquidez das ações continua em volume financeiro POR DIA (soma das barras do
  dia), não por barra. Os textos das condições passaram a falar em "barras" (1 barra = 1 dia em D1, 4 h em H4).
- A varredura só baixa o que algum setup habilitado do mercado usa. `as_of` ganha chaves `mercado:H4` (início da barra, UTC) e os
  erros de H4 levam o sufixo " (H4)". `symbols_ok` conta o ativo como avaliado só se todos os timeframes usados deram certo.
- Tela: seletor de timeframe no editor, selo D1/H4 nos setups e achados, filtro D1/H4 na lista, "Duplicar em H4" para copiar um setup,
  horário da barra no fuso da grade (NY ou UTC). Abrir um achado H4 abre o gráfico do TradingView em 4 horas; a ficha (indicadores,
  probabilidade, correlação) segue diária.
- Verificação: barras conferidas à mão contra as barras de 1 hora (NVDA, EURUSD, ouro) e RSI/preço de um achado real (DHR H4) idênticos
  a uma reconstrução independente (laço manual + RSI de Wilder escrito à mão). Ainda não se mediu se H4 acerta mais ou menos do que D1:
  isso é para o diário e a Revisão responderem.

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

Implementação (v0.5):
- **Provedor: OpenRouter** (decisão do usuário), por HTTP direto com a biblioteca padrão, no formato de chat da OpenAI; a chave vem de
  `OPENROUTER_API_KEY` no `.env`. O modelo é configurável (`AI_MODEL`, padrão `anthropic/claude-sonnet-5.5`, US$ 2/10 por milhão de
  tokens; `anthropic/claude-haiku-5.5` custa US$ 0,10/0,50).
- Lentes: ações = macro, fundamentalista, indicadores, price action; forex = macro e fundamentos, indicadores, price action;
  cripto = referência (BTC, risco, dólar), indicadores, price action. Uma chamada por lente, em paralelo; cada lente recebe só as
  suas fatias do pacote (isolamento comprovado por teste). Se uma lente falha, as outras seguem; só falha tudo se todas falharem.
- Pacote montado por código: indicadores (valores, últimas 10 leituras de RSI e histograma, probabilidade condicional), price
  action (topos e fundos, suporte e resistência em ATR, range de 52 semanas, 30 últimas barras), macro (dólar, juros, VIX,
  índices, commodities e cripto, a partir do universo de correlação), correlação (referências fixas, descobertas estáveis,
  parecer do código), fundamentos (Yahoo: múltiplos, margens, crescimento, próximo resultado; analistas separados como opinião de
  terceiros). Ficam de fora e são declarados como lacuna: calendário econômico, inflação, taxas de outros bancos centrais e notícias.
- Saída em JSON por esquema (`response_format: json_schema` com `provider.require_parameters`), validada de novo pelo app:
  inclinação (para_alta, para_baixa, indistinta, sem_dados), confiança, resumo, evidências (campo, valor, leitura, aponta_para),
  lacunas e o que mudaria a conclusão. Não existe campo de veredito, nota ou recomendação.
- **Citações conferidas por código**: cada evidência cita um caminho do pacote e um valor; o app resolve o caminho e compara
  (com tolerância de arredondamento e de % × fração). Citação que não existe ou não bate aparece com ⚠ na tela.
- Prompts fixos e versionados (v1): texto-base + nota do mercado + instruções da lente; a versão e uma impressão digital (SHA-256) dos
  textos e do esquema são gravadas em cada análise, e um teste trava o hash da v1 (editar um prompt publicado exige uma v2).
- Custo real vem de `usage.cost` da OpenRouter e é gravado por análise. O raciocínio do Sonnet 5.5 é obrigatório e cobrado como
  saída, por isso o padrão é esforço `low` (`AI_REASONING_EFFORT`); se a resposta for cortada pelo limite, o erro orienta o ajuste.
- Erros tratados com mensagem própria: sem chave, chave recusada (401), sem saldo (402), limite (429, com novas tentativas), provedor
  fora do ar (5xx, com novas tentativas), resposta truncada, recusa, JSON fora do formato.
- Privacidade: só o pacote de dados de mercado é enviado; nada do diário (teses, notas, decisões) sai do computador.
- O resumo das lentes (inclinação e confiança) vai no `snapshot.ai` do registro do diário.
- Verificado até 2026-10-22 com um servidor local que imita a OpenRouter (caminho HTTP, retentativas, erro isolado por lente,
  citações inventadas sendo marcadas) e com pacotes reais de NVDA, BTC e EURUSD. **Ainda não houve chamada a um modelo real**:
  a primeira análise com a chave do usuário deve ser conferida (custo, tempo e qualidade das respostas).

## 8. Diário e medição de acerto

Registro por ativo/decisão: decisão (entrei / não entrei / observando), tese, invalidação, alvo, horizonte,
snapshot completo (dados + vieses dos blocos + respostas das lentes + versão do prompt).

**Acerto da tese (sem falar de lucro):** alvo atingido antes da invalidação dentro do horizonte = acerto;
invalidação primeiro = erro; expirou = neutro. Medido em R (múltiplos do risco), não em dinheiro.

- **Saída antecipada**: registra o motivo e continua acompanhando o preço, mostrando o que teria acontecido mantendo o plano.
- **Ignorados** (setups listados que o usuário não tomou) também são acompanhados.
- **Revisão**: acerto por mercado; por bloco de código e por lente de IA (quando disse X, quanto acertou?);
  quando o usuário discordou de um bloco, quem estava certo; saída antecipada vs manter.

Implementação (v0.6): aba **Revisão** (`GET /api/review`), tudo calculado por código a partir do diário e dos alertas.
- **Métrica**: acerto da tese = alvo ÷ (alvo + invalidada); expiradas e abertas ficam fora da taxa, mas aparecem. Toda taxa sai com o n e
  o intervalo de Wilson; o rótulo de amostra é "insuficiente" (< 10 resolvidas), "pequena" (< 30) ou "ok". Não há score nem veredito.
- **Por tipo de decisão**: entrei / não entrei / observando, com a taxa de acerto da tese e a "decisão certa" (entrar e a tese bater o
  alvo; ficar de fora e a tese ser invalidada). Compara os que entrou com os que deixou de fora (diferença com intervalo de Newcombe) e
  conta, nas saídas antecipadas, o que a tese fez depois. Boa decisão com resultado ruim existe e o quadro não separa as duas coisas.
- **Por mercado** e **por setup** (os nomes gravados no registro; um registro com dois setups conta nos dois).
- **Por bloco de código** (regras `blocos-v1`, lidas na revisão a partir dos valores brutos do snapshot, não de rótulos congelados):
  probabilidade (rótulo da ficha), tendência (preço × MM20 × MM50), MACD (sinal do histograma), price action (estrutura de topos e
  fundos) e correlação com S&P 500 e com DXY (só se a relação é "estável": sinal da correlação × movimento de 20 dias da referência).
  RSI não aponta lado sozinho (a leitura dele está no estado da probabilidade). Relação mecânica não se aplica.
- **Por lente de IA**: a inclinação de cada lente em `snapshot.ai`, mais as versões de prompt e modelo misturadas na amostra.
- **A pergunta de blocos e lentes** é "a tese bateu o alvo mais vezes quando o bloco concordava com ela do que quando discordava?": se o
  bloco não soubesse nada, as duas taxas seriam iguais. A diferença vem com intervalo; só vira "distinguível" com ≥ 10 resolvidas em cada
  lado e o intervalo fora do zero. Registros sem o bloco (anteriores à v0.6, ou que não se aplica) ficam fora e são contados.
- **Alertas**: criados, disparados e respostas por tipo; só o alerta de **entrada** tem desfecho a medir (o que a tese fez depois da
  resposta). Alvo e invalidação disparam quando a tese termina, então medir seria circular; avulsos não têm plano.
- O snapshot passou a guardar `price_action` (resumo compacto) e `correlation` (leitura das duas referências fixas).
- Limites: dezenas de comparações com 95% geram falsos "distinguíveis" por acaso (a tela avisa); o desfecho é medido desde o registro,
  sem exigir toque na entrada; registros do mesmo ativo em datas próximas não são independentes. Verificado com dados sintéticos e
  conferido contra uma contagem independente em SQLite; com dados reais só dá para ler depois de dezenas de teses resolvidas.

## 9. Memória da IA (a gravação começou no dia 1; implementada na v0.8)

A IA não aprende sozinha; o app lembra e devolve contexto:
1. Registro de tudo (seção 8).
2. **Pós-mortem** quando a tese falha ou há saída antecipada: chamada com o pacote original, respostas das lentes e o caminho do preço depois;
   causa numa lista fixa (evento macro, referência divergiu, indicador deu ruído, invalidação ignorada, entrada tardia, sem causa identificável),
   separando o que era visível na época do que só ficou claro depois.
3. **Recuperação**: nas análises seguintes entram 3–5 casos semelhantes e estatísticas.
4. **Alertas estatísticos calculados por código**, sempre com o número de casos. A IA só pode sugerir hipótese, marcada como hipótese.

Limites conhecidos: viés retrospectivo e histórias plausíveis (daí a lista fixa e o "sem causa"); poucos casos = indício, não regra
(pensar em dezenas); o prompt só muda quando o usuário revisar e subir nova versão.

Implementação (v0.8): aba **Memória**, cartão "Memória do diário" na ficha, pós-mortem no Diário e opção de memória na análise.
- **Pós-mortem** (`memory/postmortem.py`): uma chamada por caso, só sob demanda e confirmada na tela (custa dinheiro). Elegível: tese
  `invalidada` e/ou saída antecipada registrada (qualquer decisão: uma tese que falhou num "não entrei" também ensina). O pacote tem
  `caso` (plano, desfecho, tese e motivo de saída do operador), `visivel_na_epoca` (snapshot do registro, leitura dos blocos de
  código em relação à direção da tese, lentes de IA da época, "esticado": variação de 5 e 20 dias a favor, distância da MM20 em ATR, RSI)
  e `depois` (caminho do preço e referências). Contra o viés retrospectivo, os dois blocos são separados e o prompt exige que "visível na
  época" só use o primeiro.
- **Caminho do preço** (`memory/path.py`, só código): excursão a favor e contra em R, primeiro toque na invalidação e no alvo, trajetória
  diária em R (até 30 pontos), e para saída antecipada: se a invalidação já tinha sido tocada antes da saída, e o que o preço fez depois
  (alvo, invalidação, melhor e pior ponto). Barras de 1 hora até ~700 dias, diário depois. **Referências** (dólar, juros, VIX, índices,
  commodities, bitcoin): variação entre o último fechamento das 16h NY completo antes do registro e o último antes do fim do caso;
  um caso de poucas horas sem nenhum fechamento no meio fica sem referências (usar o fechamento do dia seria olhar para o futuro, defeito
  achado e corrigido durante a verificação). "Notável" = ≥ 3% (VIX ≥ 15%; juros ≥ 0,15 ponto), heurística do app.
- **Lista fixa `causas-v1`** (`memory/causes.py`): evento_macro, referencia_divergiu, indicador_deu_ruido, invalidacao_ignorada,
  entrada_tardia, sem_causa_identificavel; mais a visibilidade (visível na época, só ficou claro depois, misto, não se aplica). Esquema
  de saída estrito, e a causa fora da lista invalida a resposta. Prompt `pm-v1` + esquema + lista entram numa impressão digital travada por teste.
- **Verificações de código** sobre a resposta (avisos ao lado dela, nunca escondidos): citações conferidas contra o pacote; causa que não se
  aplica à decisão; "invalidação ignorada" sem saída registrada depois do toque; "evento macro" sem referência notável; "entrada tardia" sem
  movimento a favor antes; incoerências (sem causa com secundárias, visibilidade × listas).
- **Casos parecidos** (`memory/similar.py`): pontuação aberta, com motivos: mesmo ativo 3, mesmo mercado 1, setup em comum 2, mesma direção 1
  (quando conhecida) e 1 por bloco de código com o mesmo lado (alta/baixa; "indistinta" nos dois não conta). Corte de 3 pontos, até 5 casos,
  e o resumo estatístico usa todos os que passam do corte (por direção).
- **Alertas estatísticos** (`memory/patterns.py`): reaproveitam as contas da Revisão (Wilson, Newcombe). Cada alerta compara um grupo com o resto
  (setup, mercado), ou entrou × fora, saída antecipada × mantida, bloco/lente concordando × discordando; só existe com ≥ 10 resolvidas em cada
  lado e diferença fora do zero; o espelho (grupo contra o resto quando o resto é outro grupo) não vira segundo alerta. A resposta traz
  quantas comparações foram testadas e quantas o acaso sozinho produziria (5%). A distribuição das causas apontadas pela IA é só uma tabela
  (classificação da IA, não medição). Hipóteses da IA nunca viram alerta.
- **Memória na análise com IA** (opção desligada por padrão): usa o prompt **v2** = v1 + a regra 9 sobre `dados.memoria`; a v1 continua o
  padrão e seu hash segue travado (`a699a8d904ba`), o da v2 também (`a47ba1b6f18c`). A fatia `memoria` leva casos parecidos, estatísticas e
  avisos, e cada lente recebe só o que ela mesma disse nos casos (isolamento comprovado por teste).
- **Privacidade (decisão a rever pelo usuário)**: a memória na análise é estruturada e sem texto livre (nada de tese, notas, motivo de saída,
  decisão ou preços; teste procura esses campos e falha se aparecerem). O pós-mortem, ao contrário, envia a tese e o motivo da saída; a tela
  avisa antes de cada chamada e o pacote fica gravado.
- Verificação (2026-10-22): 52 testes novos, suíte de 377 (mutação: vazar a decisão ou as outras lentes derruba 3 testes); 12 teses de exemplo avaliadas
  contra preços reais pelo próprio app, universo de correlação real, pós-mortem e análise com memória contra um servidor que imita a
  OpenRouter (HTTP real). O VIX citado num pós-mortem (+21,31% de 15 a 16/10) bate com o fechamento diário do Yahoo (+21,45%). **Nenhum
  modelo real foi chamado**: a qualidade das causas escolhidas, o custo e o tempo reais ainda precisam ser conferidos com a chave do usuário.

## 10. Alertas de preço

- Alerta avulso: ativo, preço, direção (cruzar acima/abaixo), nota.
- Os níveis do plano no diário (entrada, invalidação, alvo) viram alertas automaticamente.
- Ao disparar: grava hora e preço e pergunta o que o usuário fez (entrei / ignorei).
- Detecção por máxima/mínima do intervalo, não só pelo último preço.
- **O atraso do alerta é o atraso do dado.** Para preço exato é preciso fonte em tempo real.
- Só dispara com o app ligado. Notificação no Windows; opcional: bot do Telegram (token criado pelo usuário; implementado na v0.9).

Implementação (v0.9): **Telegram** (`alerts/telegram.py`, `routes/telegram.py`).
- Cada disparo vira, além do toast do Windows, uma mensagem num bot do usuário (token em `TELEGRAM_BOT_TOKEN` no `.env`). O app só ENVIA
  (`sendMessage`, HTML com todo texto livre escapado); não faz polling nem responde a comandos. Cliente por `urllib`, sem dependências.
- **Vínculo do chat** (decisão): o usuário escreve ao bot, o app lista as conversas vistas por `getUpdates` e o usuário ESCOLHE; o app não pega a mais
  recente, para que um desconhecido que ache o bot não sequestre os avisos. `link` só aceita um chat da lista e confirma com uma mensagem nele.
  O id vai para uma tabela `settings` (chave/valor, sem segredos); `TELEGRAM_CHAT_ID` no `.env` tem prioridade.
- **Token**: só no `.env`. Nunca em resposta da API, no banco, em log nem em erro: a URL da API o carrega, então toda exceção é reescrita sem a
  causa original (`raise ... from None`) e o texto passa por `scrub`. Teste: o token não aparece em nenhuma resposta, e remover o `scrub` derruba 3 testes.
- **Independência**: toast e Telegram são independentes entre si e do registro do disparo; erro de rede ou do Telegram nunca derruba o ciclo.
  Colunas novas em `alerts`: `telegram_ok` (NULL = não tentado), `telegram_detail`, `telegram_at`, `telegram_tries` (migração automática).
- **Reenvio**: espera crescente de 1, 2, 5, 15 e 60 min entre tentativas, no máximo 6 no total, só para alertas disparados nas últimas 24 h,
  usando o relógio do ciclo da vigilância. Defeito achado no teste e corrigido: a primeira versão reenviava no mesmo ciclo da falha. Ligar o Telegram
  depois não reenvia o que disparou antes (`telegram_ok` NULL não é "falhou").
- Preço sem notação científica e sem perder casas (o `:g` virava 81180.23 em 81180.2); o toast passou a usar o mesmo formato.
- Verificado com HTTP real contra um servidor que imita a API do Bot: vínculo escolhendo a conversa certa entre duas, mensagem de teste, alerta real
  de BTC e ETH disparado por barras reais da Binance, falha simulada (403) e reenvio depois da espera, token ausente do banco e do log. **Nenhuma
  mensagem foi enviada ao Telegram de verdade**: o primeiro envio real, com o bot do usuário, ainda precisa ser conferido (formato HTML no aplicativo, notificação no celular).

Implementação (v0.4):
- A vigilância roda dentro do servidor (thread em segundo plano, a cada 60 s; `ALERT_POLL_SECONDS`). Só vigia com o app ligado;
  ao ligar, o primeiro ciclo cobre o período em que ficou desligado, com barras de 1 min (até 36 h), 1 h (até 25 dias) ou 1 dia.
- Dispara pela máxima (alerta "acima") ou mínima ("abaixo") das barras de 1 min que começam depois da criação do alerta; cada
  alerta dispara uma só vez.
- Alerta avulso exige direção coerente com o preço atual (acima só se o preço está abaixo do nível).
- Níveis do plano: "entrei" → invalidação e alvo; "observando" → também a entrada, se estiver a mais de 0,1% do preço atual;
  "não entrei" → nenhum. Quando alvo ou invalidação dispara, o outro é cancelado; ao encerrar a tese, registrar saída antecipada
  ou excluir o registro, os alertas do plano são cancelados.
- Notificação: toast do Windows via PowerShell (sem dependências); clicar abre o app. Botão "Testar notificação" na tela.
- Ao disparar, o app pergunta o que o usuário fez (entrei / ignorei / observando) e guarda a resposta; o contador de pendentes
  aparece na aba e no título da janela.
- Atraso medido em 22/10/2026 (barras de 1 min): cripto (Binance) 0,5 min; ações dos EUA (Yahoo) 0,5 min; EURUSD 1,5 min;
  ouro (futuro) 10,5 min; em medição anterior, DXY ~11 min e DAX ~16 min.
- Validado com dados reais: detecção por pavio (fechamento acima do nível, mínima tocando) e recuperação de 3 dias de janela.
- Não implementado: Telegram e e-mail.

## 11. Gráficos

- Gráfico de preço: **widget do TradingView embutido por iframe** (gratuito, hospedado por eles, dados deles).
  Limites: só exibição (o código não lê os valores nem desenha níveis do usuário nele); atraso varia por mercado
  (não confirmado quais são tempo real no plano gratuito); termos de atribuição não confirmados; o preço do widget pode diferir um pouco da nossa fonte.
- Gráficos próprios só para o painel de correlação.
- O widget abre sempre com o **Supertrend** (`studies: ["STD;Supertrend"]`, o do próprio TradingView, ATR 10 e fator 3), por pedido do usuário.
  O identificador não está na documentação do widget: foi confirmado testando (a legenda "Supertrend 10 3" e as faixas aparecem). É só
  visual: o app não lê o valor do indicador, então ele não entra nos blocos de código, na probabilidade, no scanner nem na revisão.
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
4. Painel de revisão (acerto por bloco/lente) e alertas de preço. *(feito: v0.4 alertas, v0.6 revisão; H4 nos setups: v0.7)*
5. Memória: pós-mortem, recuperação e alertas estatísticos (depende de casos fechados). *(feito na v0.8; os alertas só aparecem com dezenas de teses resolvidas)*

## 17. Em aberto

- Corretora de forex do usuário (define a fonte de forex e o ouro).
- Lista de ativos de cada mercado.
- Definição dos setups, dos estados de cada bloco e do horizonte N usados na probabilidade (defaults a combinar).
- Limites e termos das fontes (seção 12) e do widget TradingView (seção 11).
- Canal de notificação dos alertas (Windows, Telegram).

Nota: ferramenta de apoio à decisão do próprio usuário; não é recomendação de investimento.
