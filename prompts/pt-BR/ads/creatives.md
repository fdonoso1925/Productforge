Crie $count variações de criativo (imagem estática + copy do anúncio) para o ângulo `angle` e o avatar `avatar`, do produto de `brief`. Todo o copy vai em português do Brasil.

Cada variação tem:
- template_id: um de `allowed_templates` (varie de template entre as variações quando puder).
- variant_note: em uma frase, o que esta variação testa em relação às outras.
- image (texto que vai dentro da imagem):
  - headline: no máximo $headline_words palavras. É o hook: lê-se em 2 segundos, sem sinais de mais.
  - subheadline: no máximo $sub_words palavras (pode ficar vazio).
  - kicker: no máximo 4 palavras (etiqueta acima do título; pode ficar vazio).
  - bullets: entre 3 e 5 itens de no máximo 7 palavras, só se o template usar lista (veja abaixo); caso contrário, lista vazia.
  - cta_text: no máximo 4 palavras (por exemplo «Quero começar hoje»).
  - price_text: só se `brief.price_text` existir, exatamente como está; senão, vazio.
  - note: só para o template `note`, 1 a 3 frases curtas com voz próxima; senão, vazio.
  - mark: `check` (benefícios) ou `cross` (erros ou coisas a evitar) para o template `checklist`.
- ad (texto do anúncio no Gerenciador de Anúncios):
  - primary_short: no máximo 125 caracteres.
  - primary_long: entre 300 e 600 caracteres, com uma mini história ou situação, os benefícios e uma chamada para ação.
  - headline: no máximo 40 caracteres.
  - description: no máximo 30 caracteres.
  - cta: um de LEARN_MORE, SHOP_NOW, GET_OFFER, DOWNLOAD, SIGN_UP.
- scene (obrigatório): a FOTO DE FUNDO do anúncio, em uma frase. Todos os anúncios levam foto de fundo, nunca uma cor lisa: escolha uma cena concreta, atraente e emocional que faça parar o scroll (uma pessoa numa situação reconhecível, um lugar, um espaço de trabalho ou da casa, natureza…). Sem texto, logos nem marcas visíveis. Em nichos sensíveis (saúde, dinheiro, dívidas, maternidade…) sem pessoas reconhecíveis: use lugares, objetos ou paisagens. Cada variação usa uma cena diferente.
- stock_keywords (obrigatório): 2 ou 3 palavras-chave EM INGLÊS, substantivos concretos que rendam bons resultados num banco de fotos (por exemplo «home office», «sunrise mountain», «coffee desk»). A foto vai atrás do texto, então busque cenas com espaço livre.
- proof_id: o `id` da prova de `proofs` que você usar (depoimento ou dado real) ou null. Se `angle.needs` for `proof`, use só provas de `proofs` e cite-as exatamente.

Uso dos campos de `image` conforme o template (os não citados ficam vazios):
- `headline_bold`, `question`, `photo_headline`: headline (em `question`, uma pergunta de verdade), subheadline, kicker e cta_text.
- `product_mockup`: headline, subheadline, 3 a 5 bullets, price_text (se houver preço) e cta_text.
- `checklist`: headline, 3 a 5 bullets e mark.
- `note`: note (obrigatório) e, se quiser, subheadline como assinatura.
- `text_post`: headline como texto de um post em primeira pessoa, subheadline e cta_text.
- `notification`: kicker (título da notificação, genérico, sem marcas), headline (a mensagem) e subheadline (uma segunda notificação).
- `before_after` e `comparison`: headline e exatamente 2 ou 4 bullets; a primeira metade é o antes ou o de sempre e a segunda metade é o depois ou com o método. Sem números nem resultados que não estejam no brief.
- `offer_stack`: headline, 3 a 5 bullets com o que está incluso (só coisas do brief), price_text exatamente como está e cta_text. Só se houver preço.
- `testimonial`: proof_id obrigatório; note = citação TEXTUAL (ou um trecho textual) dessa prova; subheadline = o autor da prova exatamente como está (ou vazio); headline = uma frase curta que apresenta a citação.

Iteração: se `iterate_from` existir, é um criativo que já foi testado (com suas métricas, se houver). Mantenha o ângulo e o avatar e proponha hooks NOVOS que testem outro enfoque (outra dor concreta, outro formato de gancho, outro prazo real); não reutilize as frases dele nem mude só algumas palavras. Se teve bom CTR, preserve o que funcionou (clareza, especificidade) e varie o resto.

Regras:
- Respeite o formato do ângulo (`angle.hook`) e adapte-o ao avatar e à linguagem dele (`avatar.language`).
- Cada variação precisa ter um hook diferente, não a mesma frase reescrita.
- Cumpra as políticas do sistema: nada sobre atributos pessoais do espectador, nada inventado (números, depoimentos, marcas), nada de urgência a menos que `real_urgency` exista.
- Texto curto e legível no celular: prefira poucas palavras de alto impacto.
