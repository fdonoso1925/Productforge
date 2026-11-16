Escreva o roteiro de um vídeo curto de motion graphics (texto e ícones animados, sem voz nem pessoas) para Reels e o feed da Meta, do produto de `brief`, para o ângulo `angle` e o avatar `avatar`. Tudo em português do Brasil, como um brasileiro escreveria.

O vídeo dura uns 17 segundos e tem 5 cenas fixas. Cada texto aparece grande na tela: poucas palavras, de alto impacto, que se leiam no celular sem pausar.

1. Gancho (0–3 s): precisa estar completo antes dos 2 segundos.
   - hook_tag: etiqueta curta de 2 a 4 palavras que chame o público (por exemplo «Atenção, tutor», «Se você empreende em casa»). Sem apontar atributos pessoais sensíveis.
   - hook_lines: o gancho dividido em 2 ou 3 linhas de 1 a 4 palavras cada, seguindo o formato do ângulo (`angle.hook`) e a linguagem do avatar (`avatar.language`).
   - hook_highlight: o índice (0, 1 ou 2) da linha que carrega a emoção; essa linha aparece grande sobre um bloco de cor.
2. Problema: problem_title (3 a 8 palavras) e exatamente 3 problems, frustrações reais do avatar em no máximo 7 palavras cada. Use formulações prudentes («pode», «muitas vezes»), sem afirmações absolutas sobre outros produtos nem marcas.
3. Solução: solution_title (2 a 5 palavras, abre a solução), solution_big (1 a 3 palavras-chave, a ideia central do produto) e solution_caption (6 a 14 palavras sobre o que ele resolve, sem prometer resultados garantidos).
4. O que você recebe: benefits_title (2 a 5 palavras) e exatamente 3 benefits com title (2 a 4 palavras) e detail (3 a 8 palavras). Só entregáveis que existem em `brief` (o produto, a promessa e os bonuses): não invente módulos, bônus nem extras.
5. Fechamento: cta_button no imperativo e em primeira pessoa, 2 a 4 palavras («Quero o guia», «Quero começar hoje»), e cta_sub, uma linha de confiança VERDADEIRA de 2 a 8 palavras («Acesso imediato após a compra», «Material digital para baixar»). Se `brief.price_text` existir, pode usá-lo exatamente como está; se não, não fale de preço.

Se existir `winning_hook`, é o título de um anúncio que já funcionou: inspire-se no enfoque dele para o gancho, com palavras novas.

Regras:
- Nada inventado: nenhum número, prazo, porcentagem, quantidade de pessoas, depoimento, estudo nem marca que não esteja em `brief`. Se um número não aparece em `brief`, não o use.
- Nada de urgência ou escassez, a não ser que `brief.real_urgency` exista.
- Cumpra as políticas da Meta: sem promessas de saúde, peso, beleza ou renda; sem apontar atributos pessoais («Você tem dívidas?», «Sofre de ansiedade?»).
- Sem asteriscos, emojis nem símbolos decorativos: o design já destaca o que importa.
