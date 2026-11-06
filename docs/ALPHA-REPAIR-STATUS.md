# S10 normal: revisão dos erros conhecidos

Alvo: SM-G973F / beyond1lte. Objetivo: um único ZIP completo de alpha para
validação no aparelho, preservando a base e o empacotamento Artisan.

## Evidência disponível

- Build anterior 42113224237: bloqueado no preflight; nenhum ZIP produzido.
- Replay real 42129937046, revisão a3e878f: sete casos passaram e cinco
  ficaram indisponíveis. O sucesso do job NÃO significa aprovação da ROM.
- Validação de fontes 42129936965: sucesso; 129 testes locais passaram.
- Coleta 42129937083: em execução quando esta revisão foi escrita; somente
  preparação do doador e preservação de inputs privados. Não é build de ROM.

## Todos os 23 eventos de falha do relatório anterior

Os eventos incluem duplicação entre falha de um patch e de seu módulo.
"Implementado" significa que existe uma correção em código, NÃO que o
módulo inteiro tenha passado com o doador real depois da correção.

| # | Evento anterior | Situação verificada nesta revisão |
|---|---|---|
| 1 | product_feature: caminho SecDisplayUtils | Resolução de caminho implementada; módulo real precisa ser reexecutado |
| 2 | RRO: rounded.xml ausente | Tratamento de recurso obsoleto implementado; módulo real precisa ser reexecutado |
| 3 | signature: patch com classes em outro DEX | Resolução por descritor implementada; aplicação integral real ainda não comprovada |
| 4 | signature: módulo/sed com caminho fixo | Resolução de runtime implementada; módulo real precisa ser reexecutado |
| 5 | Telecom SamsungBluetoothRouteManager | PASS no input real retido |
| 6 | câmera: libstagefright Video SVC | PENDENTE: sequência antiga ausente; precisa analisar o binário real e adaptar o patch |
| 7 | Extra Dim: SecSettings | Resolução por descritor implementada; patch real ainda não comprovado |
| 8 | Extra Dim: SystemUI | Resolução por descritor implementada; patch real ainda não comprovado |
| 9 | AppLock CoreRune | PASS no input real retido |
| 10 | CSC: NotificationsItem | Resolução de runtime implementada; módulo real precisa ser reexecutado |
| 11 | DeKnox: Blockchain | Rebase estrito para Lambda11 implementado; snapshot necessário indisponível |
| 12 | DeKnox: MPOS | Rebase estrito para Lambda11 implementado; snapshot necessário indisponível |
| 13 | DeKnox: SemService | Rebase estrito para Lambda11 implementado; snapshot necessário indisponível |
| 14 | DeKnox: serviço HDM | PASS de aplicação no input real retido; não comprova segurança de execução/boot |
| 15 | DeKnox: versões em knoxsdk | PASS no input real retido |
| 16 | DeKnox: DualDAR em SecSettings | Adaptação implementada; snapshot exato indisponível |
| 17 | DeKnox: HDM em SecSettings | Adaptação implementada; snapshot exato indisponível |
| 18 | DeKnox: eSE COS em SecSettings | Resolução por descritor implementada; patch real ainda não comprovado |
| 19 | DeKnox: versões em Settings Intelligence | PASS no input real retido |
| 20 | DeKnox: versões em Storage Manager | PASS no input real retido |
| 21 | KnoxPatch: AttestParameterSpec / ICD | Resolução por descritor implementada; patch real ainda não comprovado |
| 22 | KnoxPatch: SAK em DarManagerService | PASS no input real retido |
| 23 | Settings: BatteryRegulatoryPreferenceController | Resolução de runtime implementada; módulo real precisa ser reexecutado |

## Caminho até a alpha

1. Terminar a coleta já em execução e analisar libstagefright com endereços
   virtuais e saltos AArch64 reais; candidatos do analisador não autorizam
   substituição de bytes e não são uma correção nativa.
2. Validar os rebases e os patches pendentes contra os JARs/APKs reais,
   reaproveitando os arquivos privados capturados, sem novo download do firmware.
3. Com os bloqueios conhecidos de compilação resolvidos, iniciar a alpha
   completa, incluindo preflight de todos os módulos, recompilação dos APKs,
   kernel, imagens e ZIP único. Falhas nessas etapas continuam sendo possíveis;
   testes de fontes não as antecipam integralmente.
4. Entregar o ZIP completo com checksum e aviso de alpha não validada no
   aparelho. Corrigir problemas de boot e funcionamento com logs do teste real.

Não se exige perfeição funcional para uma alpha. Exige-se que os patches e o
empacotamento terminem corretamente: desabilitar módulos, ignorar falhas ou
empacotar uma árvore parcialmente alterada não produz uma alpha confiável.

## Falha posterior da alpha experimental 42137760729

O preflight chegou ao final em modo experimental (47 módulos, 46 tentativas,
20 falhas registradas) e a execução avançou para a reconstrução dos JARs.
O bloqueio fatal foi `services.jar`: `smali a -a 36` gerou
`IllegalArgumentException: dexVersion must be within [0, 999]`.

Causa confirmada no pin google/smali
8be50d709f10d384f2adc9a6e15bd525067d75a3, classe VersionMap:
mapApiToDexVersion(36) retorna NO_VERSION (-1); o maior mapeamento suportado
é API35 -> DEX041. O overlay forçava API36 em todos os DEX de services.jar.

Correção: remover o override por nome de JAR e preservar a API derivada do
header de cada DEX. Rejeitar metadados de montagem acima de API35, em vez de
invocar uma montagem impossível. Não altera o SDK declarado da ROM nem
rebaixa todos os JARs para um formato fixo. Os testes exercitam services.jar
com dois formatos distintos e impedem a regressão do override API36.

Foi adicionado um smoke test com o Smali compilado de verdade, ANTES do
download dos firmwares: monta uma classe mínima em cada formato suportado
035/037/038/039/040/041 e verifica magic, tamanho, SHA1 e Adler32 do DEX.
Os testes locais do smoke usam um mock do Java; só a etapa no runner prova
a execução do JAR real. O resultado local desta revisão é 138 testes PASS.
Ainda não equivale a sucesso de reconstrução dos JARs reais nem boot.
