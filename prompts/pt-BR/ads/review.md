Revise cada criativo de `creatives` (numerados com `index`) e devolva, para cada um, um semáforo de políticas e um pré-score.

**Políticas.** Aplique este checklist (`strict` indica um nicho sensível: seja mais rigoroso):

$checklist

Para cada criativo:
- policy.status: `green` (cumpre), `yellow` (revisar: dúvida razoável) ou `red` (bloquear: infringe uma regra).
- policy.notes: uma nota por problema, com a regra e o motivo em uma frase. Vazio se for `green`.
- policy.rewrite: se não for `green`, uma reescrita sugerida do título (ou do texto problemático) que mantenha a ideia sem infringir; se for `green`, vazio.

**Pré-score (1 a 10).** Pontue cada critério de 1 a 10 e dê um `score` global (não é a média exata: pondere o hook e o risco):
- hook_clarity: entende-se em menos de 2 segundos.
- specificity: é concreto (resultado, prazo, público) e não genérico.
- avatar_relevance: fala com o avatar indicado em `avatar`.
- visual_contrast: o texto e a composição se leem com alto contraste.
- mobile_legibility: lê-se bem no celular (poucas palavras, título curto).
- policy_risk: 10 = sem risco, 1 = risco alto.
- explanation: uma frase que explica a pontuação.
- improvement: uma melhoria concreta e acionável.

Seja honesto e exigente: uma nota alta deve ser rara.
