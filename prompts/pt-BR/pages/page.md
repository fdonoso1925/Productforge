Escreva a página de vendas completa do produto de `brief`, pensada para converter visitas em compradores. Ela será vista primeiro no celular.

Dados disponíveis em <dados_do_usuario>:
- `brief`: produto, público, problema, dor, promessa, prazo, por que pagariam e as peças do pacote (`deliverables`: a principal, os bônus e os order bumps). `price_text`, `guarantee_text` e `real_urgency` existem só se o usuário informou.
- `angles`: os ângulos de venda possíveis. Use todos os que se aplicarem ao longo da página, cada um onde funciona melhor: dor e situação no problema; mecanismo na solução; transformação no hero e no fechamento; pessoa/identificação em «é para você»; objeção nas perguntas frequentes; erro comum e mito na solução ou nos benefícios; lista de benefícios nos benefícios. Ignore os que pedem dados que não existem (oferta sem preço, autoridade sem provas, urgência sem urgência real).
- `proofs`: provas reais com seu id. Se houver, escolha as que mais ajudam em `proof.proof_ids` (não copie o texto: o sistema o insere exatamente como está) e escreva só uma frase de introdução em `proof.intro`. Se não houver, deixe `proof.proof_ids` e `proof.intro` vazios.
- `reference_teardown` (opcional): análise de outra página. Mantenha o que funciona na estrutura dela, corrija as fraquezas (`weaknesses`), acrescente o que falta (`missing`) e supere a clareza dela. Evite todos os `brand_terms`. Seu texto não deve se parecer com o dela em palavras: precisa soar como este produto e este público.
- `feedback` (opcional): problemas de uma tentativa anterior; corrija-os.

Como escrever, seção por seção:
- `hero`: `eyebrow` (para quem é, em poucas palavras), `headline` (promessa concreta; no máximo 110 caracteres), `subheadline` (como e em quanto tempo, sem exagerar), exatamente 3 `bullets` de benefício e `cta_text` (verbo + resultado, por exemplo «Quero começar agora»). `microcopy`: só fatos reais (por exemplo, acesso imediato se o produto é digital); na dúvida, vazio.
- `problem`: a situação e a dor com as palavras do público (`pains`: 3 a 6, concretos) e `agitation`: o que acontece se continuar igual, honesto e breve.
- `solution`: apresente o método. `mechanism_name`: um nome curto e descritivo (não uma marca registrada nem uma invenção pretensiosa). `mechanism`: como funciona e por que é diferente do que já tentou.
- `journey`: de 3 a 5 etapas do caminho de onde está até o resultado, cada uma com título e o que fará nessa etapa.
- `benefits`: de 4 a 6, cada um com título de resultado e um texto que explique o porquê.
- `deliverable_blurbs`: uma frase de valor para cada peça de `brief.deliverables`, na mesma ordem e na mesma quantidade. Para os bumps, apresente-os como complemento opcional.
- `for_you` (3 a 6) e `not_for_you` (2 a 4): honestos; não é para quem busca resultado sem aplicar o que aprende.
- `about`: só se `brief.about_author` trouxer dados; resuma-os sem acrescentar credenciais. Se não houver, vazio.
- `offer`: `title`, `intro` (resume o que a pessoa leva e por que é uma boa decisão, sem repetir o preço) e `cta_text`. Deixe vazios `price_text`, `guarantee` e `urgency`.
- `faq`: de 5 a 8 perguntas que eliminam as objeções reais desse público (tempo, nível, formato, acesso, se serve para o caso dele), com respostas diretas. Não fale de garantia, devolução nem pagamento se não houver `guarantee_text`.
- `final_cta`: fechamento que retoma a transformação e pede a compra.
- `disclaimer`: aviso breve e honesto (os resultados dependem de aplicar o conteúdo; não se garantem rendimentos nem resultados específicos).
- `seo_title` (até 60 caracteres) e `seo_description` (até 160).

Regras duras:
- Nenhum número (prazos, porcentagens, quantidade de pessoas ou vendas) que não esteja em `brief` ou `proofs`.
- Nada de depoimentos inventados, nomes, logos nem «milhares de pessoas».
- Os textos são para leitura rápida: frases curtas, sem enrolação nem palavras vazias.
