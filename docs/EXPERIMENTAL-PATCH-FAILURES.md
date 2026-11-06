# Alpha experimental com falhas de patches

A pedido explícito do proprietário, a requisição de build do S10 normal ativa
`experimental_patch_failures: true`. O padrão de alpha.yml continua false.
Na CLI, a opção equivalente é `BEYOUD_EXPERIMENTAL_ALLOW_PATCH_FAILURES=1`.

- O preflight continua percorrendo os módulos e registrando as falhas.
- O relatório não chama falhas de sucesso: usa `experimental-with-failures`.
- A execução real reconstrói a árvore original, tenta os patches de novo e
  registra seu próprio relatório. O diagnóstico anterior fica separado em
  `out/beyoud-logs/diagnostic-preflight.json`.
- Um patch Smali rejeitado não é aplicado à força. Continua-se após registrá-lo.
- Uma falha fatal dentro de customize.sh termina aquele módulo. O restante
  desse módulo pode NÃO ser executado; os módulos seguintes são tentados.
  Alterações já realizadas pelo módulo não são revertidas automaticamente.
- Não se ignora cobertura incompleta do preflight. Não se desliga errexit
  globalmente e não se ignora erro de compilação de APK/JAR, kernel, imagens,
  integridade de firmware ou criação do ZIP.
- A identidade dos checkpoints inclui o modo experimental: um build estrito
  não pode reutilizar silenciosamente um checkpoint desse modo.

**Não há garantia de boot.** Assinatura, Knox e mudanças parciais em serviços
podem causar bootloop, perda de funções ou outros problemas. O modo aceita
esse risco para tentar gerar uma alpha; não demonstra que os erros são
inofensivos. Mesmo nesse modo o build pode parar e nenhum ZIP ser produzido.

Para voltar ao modo estrito, remover o input true da requisição ou usar false.
