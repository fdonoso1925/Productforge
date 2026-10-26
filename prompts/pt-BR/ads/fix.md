Corrija os criativos de `creatives` para que passem na revisão de políticas da Meta SEM que seja preciso mexer neles depois. Cada um traz seu `draft` atual, as observações de políticas (`policy_notes`, com a regra, o motivo e a gravidade) e uma reescrita sugerida (`suggested_rewrite`). O objetivo é entregar anúncios que fiquem em verde: sem observações.

Checklist de políticas (`strict` indica um nicho sensível: seja mais rigoroso):

$checklist

Como corrigir:
- Resolva TODAS as observações de cada criativo, em qualquer parte do texto: a imagem (título, subtítulo, kicker, bullets, botão, nota), o texto do anúncio (`primary_short`, `primary_long`, `headline`, `description`) e a `scene`.
- Mantenha a ideia, o ângulo, o avatar e a `template_id` (não a mude). Mantenha `scene`, `stock_keywords`, `proof_id` e `variant_note`, a menos que sejam a causa da observação.
- Tire o problema pela raiz: não afirme nem insinue características pessoais de quem vê o anúncio (saúde, peso, dívidas, gravidez, religião, orientação…); fale da situação ou do público em geral. Elimine promessas garantidas, dinheiro rápido, antes/depois, números ou provas que não estejam em `proofs`, urgência que não esteja em `real_urgency` e qualquer menção a plataformas ou marcas.
- Reescreva com naturalidade: que continue sendo um anúncio atraente, específico e com um hook claro, não uma versão tímida e genérica.
- Respeite os limites de tamanho: títulos de até $headline_words palavras e subtítulos de até $sub_words palavras na imagem; os textos do anúncio com seus limites habituais. Mantenha a mesma quantidade de bullets.
- Não invente dados, depoimentos, números nem preços: só o que está em `brief` e `proofs`.

Devolva exatamente um criativo corrigido para cada elemento de `creatives`, na mesma ordem.
