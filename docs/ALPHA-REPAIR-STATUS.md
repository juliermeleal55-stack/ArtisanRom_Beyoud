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

Correção adicional da mesma revisão: DEX_TO_API lia só o byte 6 do magic,
confundindo o caractere ASCII final de 041 com compact DEX e não reconhecendo
040 corretamente. Agora compara os oito bytes completos, preserva o caso
compact DEX legado e rejeita headers desconhecidos. Testes reais de bytes
035/037/038/039/040/041 foram adicionados. Total atualizado: 139 testes PASS.

## Falha de preparação do ZIP: 42149777675

A etapa patch terminou: services.jar, framework.jar, APKs e overlays foram
reconstruídos. O job parou em retire ao tentar ler exclusivamente
ro.build.product em system/system/build.prop do S926B. O relatório de erro
anterior não distinguia ausência de valor duplicado; não há comprovação de
boot e nenhum ZIP foi produzido.

O leitor mantém a propriedade legada como preferencial, mas, se ausente,
consulta ro.product.system.device e ro.product.device no mesmo arquivo.
Na ausência das três, aceita somente o componente device de um fingerprint
Android integralmente validado (ro.system.build.fingerprint/ro.build.fingerprint).
Para o identificador de vendor, preserva ro.product.vendor.device e oferece
os equivalentes no próprio vendor/build.prop. Propriedades existentes inválidas
ou duplicadas continuam sendo erros, sem serem mascaradas por um fallback.
Não se deriva um codename do modelo SM-S926B nem se altera a identidade do S10.

A validação dos quatro identificadores e limites de imagens agora acontece
logo após a extração do stock, ANTES da compilação dos patches, e é repetida
antes da remoção dos firmwares. Testes cobrem Android moderno, firmware legado,
fingerprint, ambiguidade, valores inválidos, preservação do cache após retirement
e a proibição de apagar os firmwares se a captura falhar. Resultado local:
145 testes PASS na cópia limpa com as alterações desta revisão. A validação
com o firmware real cabe à nova execução, não aos fixtures locais.

## Falha de partições auxiliares: 42195819773

A correção de identificadores passou no firmware real; patch e retire terminaram.
Package falhou na primeira imagem, optics: o stock G973F AUT só registrou caps
para system (5976883200), vendor (1153433600) e product (650117120).
O create_work_dir Artisan copia optics/prism/odm do doador e o empacotador
original tenta transformar toda árvore reconhecida em uma partição flashável.
Não se deve aumentar/inventar caps nem usar o tamanho de uma partição do S926B
como se fosse capacidade física do S10. A ausência de uma imagem no pacote
stock por si só também não é prova absoluta de ausência física no PIT.

A normalização de layout agora roda depois da montagem real, ANTES do checkpoint
patch e de retirar os firmwares. Para optics/prism/odm que não constam nos caps
do stock, preserva integralmente a árvore em system/system/<nome>, expõe o caminho
raiz via symlink /<nome> -> /system/<nome>, remapeia fs_config/file_context mantendo
UID/GID/modos/tipos SELinux e remove entradas fstab para esses pontos de montagem
nas árvores de texto empacotadas. Não modifica o boot ramdisk compilado; não
comprova que init e SELinux funcionarão no aparelho.

Se uma partição auxiliar constar nos caps reais do stock, não é relocada.
Colisões, metadados ausentes/inesperados e outras partições não suportadas geram
falha, não descarte silencioso. Verifica-se ainda um limite inferior dos bytes
do payload antes de construir imagens; overhead ext4 e tamanho lógico final
continuam sendo verificados na construção e antes de compressão.

O coletor final também confere payloads e block_image_update contra o conjunto
de caps capturados e rejeita imagens super/init_boot/vendor_boot no pacote S10
estático. Isso não certifica a tabela física de partições nem boot. A montagem
usa somente imagens suportadas; o conteúdo auxiliar não é descartado para
fingir sucesso. Relatório: out/beyoud-logs/static-layout.json.

Testes acrescentados: conteúdo preservado, remapeamento de labels/permissões,
fstab, idempotência, colisões verificadas antes das movimentações, metadados
faltantes, partições desconhecidas, payload maior que cap, partição auxiliar
realmente registrada no stock e rejeição de payload/escrita não suportada no ZIP.

O job anterior consumiu aproximadamente 156 minutos antes das imagens finais.
O orçamento do job foi aumentado de 180 para 360 minutos para não abortar a
compressão/assinatura apenas por esse limite; não significa promessa de prazo
ou sucesso. Total local atualizado: 150 testes PASS em cópia limpa.

## Colisão ODM: 42236213796 e comparação OneROM

A reconstrução dos APKs/JARs terminou novamente. A falha foi introduzida pelo
normalizador Beyoud: tratava qualquer symlink em system/odm como colisão fatal.
A anotação antiga não preservou o tipo/alvo exato desse nó; portanto os testes
novos cobrem tanto aliases Android conhecidos quanto diretórios não vazios.

Agora um alias Android conhecido é substituído SEM seguir/apagar seu destino,
e seu valor anterior fica no relatório. Diretórios não vazios são mesclados,
preservando arquivos e metadados; arquivos/links divergentes ou metadados
conflitantes bloqueiam tudo antes de qualquer movimentação. Destinos externos
não reconhecidos continuam rejeitados. A validação completa desse plano também
roda no fim do preflight, antes da recompilação real, além da aplicação após
make_rom; assim não se espera o fim da montagem real para descobrir colisões.
Os tamanhos usam caminhos finais projetados para não contar duas vezes cópias
idênticas que serão consolidadas; as verificações das imagens permanecem.

Foi consultada novamente OneROM no pin já auditado
644f0aacc49ad2410e566de8deb05e6c8211d83d. As três evidências originais e seus
hashes Git estão em manifests/onerom-layout-review.json. O create_work_dir
continua copiando as árvores auxiliares; simplesmente copiá-lo NÃO corrige
nossa colisão. Seu layout user-repartition-20260913 declara explicitamente
que vale só para o aparelho medido e installation_approved=false; system é
7340032000 bytes, maior que os 5976883200 bytes do filesystem stock capturado
para esta integração. Esses números não foram usados como caps do aparelho
do usuário e não se importou uma repartição não aprovada para fingir sucesso.

As adaptações OneROM de serviços anteriormente importadas permanecem. Não
foram substituídos APKs/framework/kernel que já conseguiram recompilar por
blobs de outro doador. A base continua Artisan S10 e o doador S926B.

Nesta revisão: 154 testes PASS em cópia limpa e 60 evidências auditadas PASS.
Os testes extras incluem aliases absolutos/relativos, diretório ODM não vazio,
links externos rejeitados, preservação de vendor/odm, metadados conflitantes e
contagem de duplicatas no tamanho projetado. Ainda falta aplicar o novo plano
na árvore real do doador e concluir imagens/instalador. Nenhum ZIP é declarado
pronto por esses testes de fonte.

## Regressões da tentativa 42308577685

Esta tentativa falhou ainda no diagnóstico: apenas 9 patches foram tentados.
O motivo de vários "class found 0" foi anterior: o header de samsungkeystoreutils
foi lido como 003933300a786564. READ_BYTES_AT da base Artisan inverte a sequência
para uso numérico little-endian. Meu teste anterior simulava essa função como
um leitor em ordem de arquivo e não reproduziu a integração real.

DEX_TO_API agora lê bytes em ordem de arquivo com od -tx1, sem a conversão
numérica. A função original completa foi preservada/verificada como evidência
e usada no harness de regressão. O smoke test no runner agora também testa o
mapeador de scripts/apktool.sh com os DEX reais recém-montados, antes de baixar
firmwares; não valida só o Java de forma isolada.

O outro bloqueio era odm/etc: o diretório ODM legado pode conter encaminhadores
para /vendor/odm/etc ou /odm/etc. Agora são classificados como aliases de
roteamento apenas se o destino corresponder exatamente à mesma partição e ao
mesmo caminho relativo. Quando substituídos por conteúdo real do doador, remove-se
só o link, nunca o destino vendor. Aliases de vendor sem conteúdo substituto são
preservados; encaminhadores canônicos /odm/* que virariam ciclos são retirados,
com registro no relatório. Arquivos reais e diretórios divergentes continuam
sendo conflitos, e aliases externos não reconhecidos não são sobrescritos.

As checagens antes de qualquer movimento e os caps das imagens continuam ativas.
Não foram copiados limites de repartição da OneROM nem substituídos JARs/APKs
que já conseguiram recompilar na tentativa anterior. As adaptações OneROM de
serviços permanecem. Resultado local: 157 testes PASS em cópia limpa; 61
referências de auditoria PASS. Ainda não é prova de ZIP ou boot.

## Falso bloqueio do registro raiz: 42315166635

O erro "Unexpected metadata path: 0" foi causado pelo leitor Beyoud. O comando
sed real de extract_fw.sh remove o prefixo de montagem da linha de stat da
raiz: resulta em " 0 0 755 capabilities=0x0", enquanto os filhos ficam com o
prefixo da partição. A linha é válida, não uma falta de caminho a ser tratada
como corrupção. O remapeamento agora converte esse registro em metadata da
raiz do diretório embutido e preserva UID/GID/mode/capabilities.

Duplicatas semanticamente iguais (755/0755, capabilities omitido/0x0) não
bloqueiam mais. UID/GID/modos/capabilities realmente divergentes continuam sendo
conflitos. A regressão foi reproduzida executando o comando sed do extrator
pinned, não só criando um fixture imaginado. Total local: 160 testes PASS em
cópia limpa, 61 evidências auditadas PASS. Não se removeram limites de imagens
ou validação dos destinos de gravação para fabricar um resultado verde.
