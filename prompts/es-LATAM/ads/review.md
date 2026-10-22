Revisa cada creativo de `creatives` (están numerados con `index`) y devuelve, para cada uno, un semáforo de políticas y un pre-score.

**Políticas.** Aplica este checklist (`strict` indica un nicho sensible: sé más estricto):

$checklist

Para cada creativo:
- policy.status: `green` (cumple), `yellow` (revisar: duda razonable) o `red` (bloquear: infringe una regla).
- policy.notes: una nota por problema, con la regla y el motivo en una frase. Vacío si es `green`.
- policy.rewrite: si no es `green`, una reescritura sugerida del titular (o del texto problemático) que conserve la idea sin infringir; si es `green`, vacío.

**Pre-score (1 a 10).** Puntúa cada criterio de 1 a 10 y da un `score` global (no es el promedio exacto: pondera el hook y el riesgo):
- hook_clarity: se entiende en menos de 2 segundos.
- specificity: es concreto (resultado, plazo, público) y no genérico.
- avatar_relevance: le habla al avatar indicado en `avatar`.
- visual_contrast: el texto y la composición se leen con alto contraste.
- mobile_legibility: se lee bien en el celular (pocas palabras, titular corto).
- policy_risk: 10 = sin riesgo, 1 = alto riesgo.
- explanation: una frase que explica el puntaje.
- improvement: una mejora concreta y accionable.

Sé honesto y exigente: un puntaje alto debe ser raro.
