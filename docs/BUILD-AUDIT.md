> **Fluxo atual:** consulte [BUILD-STAGES.md](BUILD-STAGES.md) e
> [CROSS-AUDIT.md](CROSS-AUDIT.md). As tentativas e comandos anteriores abaixo
> são históricos; não comprovam sucesso do fluxo atual.

# Revisão dos bloqueios do pipeline

## Confirmado e corrigido

1. **Duas rotas de resolução de versão:** SmartDownload encontrava os pacotes,
   mas download **e extração** chamavam GET_LATEST_FIRMWARE via curl/perl/FOTA.
   O parser legado retornava vazio e abortava antes de baixar. Agora o probe
   emite um registro estruturado, `metadata.py` grava atomicamente
   `out/firmware-lock.json`, e o helper compartilhado lê apenas esse lock.
   Não há fallback silencioso para latest nem troca de versão durante o build.
2. **Lock parcial ou antigo:** ao começar uma nova consulta, o lock anterior é
   invalidado. Só se publica o novo quando todos os modelos/CSCs e extras
   configurados respondem com versão e tamanho válidos. Identidades divergentes,
   versões malformadas, entradas ausentes/duplicadas e tamanho inválido abortam.
3. **Erros de processos paralelos ocultos:** `wait PID1 PID2` devolve o status
   do último PID. O build agora guarda cada PID e verifica cada retorno, nas
   compilações APK/JAR, imagens de partição e conversões/compressões. Um processo
   anterior falhando não permite seguir ao ZIP como se tudo tivesse passado.
4. **Cache de workdir incompleto:** o hash de make_rom incluía só unica/target.
   Agora inclui plataforma, overlay de integração e o lock de firmware.
5. **ZIP parcial antigo:** o downloader limpa somente os ZIPs do diretório
   de firmware que ele gerencia antes de começar novo download. Não pode escolher
   um ZIP antigo por ordenação de nome após uma tentativa interrompida.
6. **Espaço não verificado:** a consulta bem-sucedida anterior encontrou pacotes
   de 18.616.749.776 bytes e 6.365.561.728 bytes. Um ZIP e sua expansão Odin podem
   coexistir. O runner hospedado libera SDKs não usados em seu ambiente descartável
   e o probe exige pelo menos `2 * maior pacote + 8 GiB` livres. É um mínimo de
   download/expansão, **não garantia de espaço para todo o port**.
7. **Duplicação do ZIP final:** o coletor usa hardlink quando possível, evitando
   copiar vários GiB no mesmo filesystem. Mantém fallback de cópia entre volumes.
   O lock de firmware acompanha o artefato e os diagnósticos.
8. **Log da ROM omitido:** o coletor de falhas publica a cauda de todos os logs,
   não apenas dos dois últimos nomes em ordem alfabética.

## Validação nesta etapa

- Testes Python cobrindo lock atômico, consulta compartilhada, falha da segunda
  origem, normalização e isolamento de identificadores, workers paralelos e ZIP.
- Aplicação dos patches aos arquivos reais da revisão fixada da ArtisanROM.
- `bash -n` nos scripts originais após transformação e nos scripts de integração.
- Testes não dependem de acessar Samsung nem presumem que o build completo passou.

## Ainda depende do firmware e da execução real

- O metadado de versão não comprova One UI 9/SDK 37. A configuração fonte declara
  SDK 37; propriedades extraídas precisam ser confrontadas antes de release.
- VNDK 34 e certas traduções de features no adapter continuam provisórios;
  não converter ESE em NFC ou suporte de tela em compatibilidade real sem evidência.
- Padrões smali da ArtisanROM antiga podem ter mudado. Não ignorar falhas nem
  remover patches para obter um ZIP aparentemente válido.
- Kernel, HALs, SELinux, VINTF e capacidade física das partições não foram testados
  no G975F. Um build completo não comprova boot ou segurança de flash.
- Dependências transitivas do kernel e disponibilidade dos servidores podem
  falhar. O pin do repositório principal não fixa todos os downloads que seus
  scripts fazem; a toolchain precisa continuar sendo auditada na execução.
- O mínimo de espaço pode ser ultrapassado durante extração, cópia de workdir,
  kernel e compressão; um runner maior pode ser necessário.

Não se declara "base toda OK" a partir desta auditoria estática. As correções
acima removem inconsistências específicas e tornam novas falhas observáveis.

## Tentativa de caber no runner Linux sem novos dados pessoais

O bloqueio observado foi 24.651.677.696 bytes livres contra mínimo calculado de
45.823.434.144 bytes. O IMEI não interfere nesse problema: as consultas Samsung
já passaram sem ele.

A limpeza ampliada é limitada ao runner **descartável hospedado pelo GitHub**,
com opt-in explícito. Remove SDKs, CodeQL, navegadores e imagens/cache Docker
não usados pelo pipeline; preserva Java, Python, Go, Rust e compiladores.
O script recusa execução local sem as duas condições de segurança. Ele não
formata, não une discos nem apaga a árvore do projeto.

O workflow compara o espaço disponível em RUNNER_TEMP e /mnt, escolhendo a
workspace em um volume maior quando existir. Todos os artefatos e diagnósticos
seguem a localização escolhida. Se os dois caminhos estiverem no mesmo volume,
isso não cria capacidade extra.

Depois da montagem, a CI descarta somente o arquivo-fonte baixado automaticamente
(cerca de 1,4 GiB), já verificado e extraído. A opção recusa apagar um arquivo
fornecido via --archive. Depois de instalar os dois executáveis Rust, remove
os intermediários Cargo release; as ferramentas instaladas permanecem no lugar.

A verificação de espaço continua ativa. São otimizações a medir na nova execução,
não garantia de que o runner comporte extração, workdir e ZIP final. O log de
armazenamento registra o antes/depois, e nenhum IMEI/serial precisa ser enviado.

## Preparação sequencial e liberação progressiva do ZIP

O fluxo antigo baixava os dois firmwares antes de extrair qualquer um. O novo
`integration/samloader/stage.py` processa fonte, destino e extras um por vez:

1. Verifica versão no lock e espaço para o próximo download.
2. Executa download e extração apenas daquele descritor, com as flags originais
   `--ignore-source --ignore-target <descritor>`.
3. Confirma a versão em `.extracted` e presença de conteúdo extraído.
4. Só então remove o diretório Odin daquele firmware, preservando `out/fw`.
5. Inicia o próximo. Em falha, não limpa o material diagnóstico nem começa outro.

Somente sequenciar não elimina o pico do ZIP de 18,6 GB coexistindo com os tar
Odin completos. Por isso, em Linux, `unpack_reclaim.py` substitui o unzip nessa
workspace descartável: extrai todos os membros, liberando com **hole punching**
os blocos comprimidos que já foram lidos. Não depende de atributos privados de
zipfile nem muda o tamanho lógico da fonte enquanto a leitura está em curso.
Todos os arquivos/partições são preservados; zipfile verifica os CRCs dos membros
e a verificação MD5 Odin original continua depois da extração ZIP.

O ZIP passa a ser **descartável a partir da primeira liberação de bloco**. Se
houver erro, ele não deve ser reutilizado: será necessário baixar novamente.
Arquivos parciais não viram saídas concluídas, o marcador `.downloaded` não é
escrito, e a falha é propagada. O fonte só é apagado após todos os CRCs passarem.
O script primeiro testa o suporte do filesystem e recusa fallback que dobre o
consumo de disco. Não é um substituto genérico para unzip de arquivos pessoais.

O cálculo inicial passa de `2 * maior pacote + 8 GiB` para `maior pacote + 8 GiB`
**porque o fluxo real foi alterado**, não porque a proteção foi desativada.
Antes da expansão, a tabela ZIP fornece o tamanho descompactado; o script
confere capacidade disponível mais blocos recuperáveis e mantém reserva de
2 GiB durante cada escrita. Há nova verificação antes de cada firmware. O lock
registra `storage_mode=sequential-linux-reclaim` para identificar essa política.

Testes executam cópia real com ZIP armazenado e deflate, incluindo membro de
18 MiB, múltiplos arquivos, CRC inválido, caminho inseguro, filesystem sem suporte
e ordem/limpeza de firmware. Os patches foram aplicados aos scripts reais da
revisão upstream e passaram em bash -n.

Ainda pode faltar espaço dentro da extração de super.img, na criação do workdir,
no kernel ou nas imagens finais; esses estágios não foram declarados resolvidos.
Não foram removidas partições nem reduzidas imagens artificialmente para caber.

## Resultado real de 2026-11-05 — execução 42079665263 (SM-G973F)

As ferramentas e os DOIS firmwares foram preparados. O preflight registrou
120.867.278.848 bytes livres; após extrair o doador, 102.732.095.488; após o
G973F, 95.388.803.072 (~95,39 GB decimais). Esse runner tinha um filesystem maior
que o das tentativas anteriores: não atribuir toda a melhora às otimizações.
Não faltou espaço nesta execução; ainda não se mediu o pico de kernel/imagens/
assinatura. Estes números não garantem espaço para qualquer tentativa futura.

O bloqueio foi `0001-Better-model-detection-in-FreecessController.patch`, em
services.jar. O hunk esperava registrador v2 e const-string/jumbo com contexto
antigo. Substituído, SOMENTE na workspace, por adaptação que identifica uma
leitura SystemProperties.get com a mesma chave e o mesmo registrador, aceita
const-string normal/jumbo e localização em outro dex, preserva o resto do
método e exige unicidade. Mantém a alteração ro.product.model ->
ro.product.vendor.model, não desativa a correção. Falha em contexto desconhecido
ou ambíguo; o código real decodificado ainda precisa confirmar a aplicabilidade
na próxima execução. Testes sintéticos não são prova de funcionamento no donor.

Revisão adicional: debloat agora trata listas vazias como sucesso, limita seus
workers e propaga explicitamente falhas do xargs. Download da toolchain do
kernel não desativa TLS e aborta em erro HTTP/descompactação, em vez de seguir
com um arquivo de erro. O arquivo baixado ainda não tem digest upstream
independente fixado: não alegamos reprodutibilidade transitiva completa.

Antes dos patches é emitido `patch-inventory.json`, distinguindo módulos
ativos/desativados, patches smali, scripts de HEX_PATCH e sites de falha ignorada.
É inventário de risco, não validação binária e não desativa módulos sozinho.
Diagnósticos de git apply preservam smali real (até 2 MiB por arquivo, restrito
à árvore decodificada da workspace) no artefato privado, para permitir adaptar
as próximas incompatibilidades sem adivinhar a partir do patch antigo.

## Execução 42087870700: Freecess passou, CoreRune bloqueou

O log confirma `Freecess model detection: adapted`. O próximo bloqueio foi o
hunk CoreRune em framework.jar (dex/registrador/contexto antigos). Foram
substituídos os DOIS reads de identidade (device/model) por adaptação guardada:
procura SystemProperties.get, valida registradores e método, exige unicidade,
valida ambas as mudanças antes de gravar. Mantém as propriedades vendor e não
ignora a correção. A procura não depende de smali_classes6.

A revisão de patches de identificação também localizou o mesmo tipo de hunk
em Settings/ModelNameGetter: preservada a mudança para ro.boot.em.model usando
a mesma validação de leitura, sem hunk fixo. Outros patches de funções/recursos
não são convertidos cegamente por não serem simples trocas de propriedade.

Outro problema observado: unzip da recuperação de recursos de framework.jar
pediu confirmação e recebeu EOF no runner sem terminal. Agora a chamada é
não interativa (-oq) e propaga falha de extração.

Não é possível continuar o job GitHub-hosted já encerrado. Somente diagnósticos
foram preservados; não há backup da workspace pesada nem cache restaurável de
firmware/árvore compilada. Checkpoints locais só permitem retomar no mesmo
filesystem persistente, com receitas compatíveis. “Re-run jobs” executa em
runner novo e não incorpora correções posteriores ao SHA original. Para testar
as correções novas, é preciso uma execução NOVA no commit corrigido, ou uma
máquina persistente preparada. Não prometer retomada instantânea desse run.

## Correção da integração APKTool após revisão 01d3173

As alterações externas tinham sido gravadas em reference/build/scripts/apktool.sh,
mas o preparador continuava exigindo o script original do archive. Isso causava
`Unexpected pinned CoreRune/apktool input`. A referência e seu Git blob ID foram
restaurados à revisão upstream; a versão adaptada agora reside explicitamente
em integration/artisan/apktool.sh e é instalada pelo framework_policy após a
validação do original. Correções de extração ZIP do outro autor foram mantidas.

O TSV por DEX agora é gravado DEPOIS de definir SMALI_OUT na mesma iteração.
Mantida a passagem única de baksmali, o orçamento BEYOUD_JOBS, os nomes de DEX
na remontagem e a política API 36 de services.jar da alteração revisada.

Novos testes executam os loops reais de decode/assembly com comandos externos
simulados: validam classes.dex e classes2.dex com APIs distintas, associação de
pastas, execução única por DEX e override services.jar. Também reproduzem a
montagem a partir do arquivo upstream intacto e verificam que a workspace
recebe o overlay, não uma referência modificada. Não são testes dos APKs reais.

## Falha HFR em 42102368559 e revisão do restante da cadeia

O doador real aceitou Freecess e CoreRune. O bloqueio seguinte foi o patch
`Remove-brightness-threshold-values`, que esperava `SEAMLESS_BRT: 89,91` e
`SEAMLESS_LUX: 260,2500`. Esses números de outro firmware não são uma interface
estável. A substituição guardada em integration/refresh_rate.py identifica
getMainInstance e o construtor BrightnessThreshold de quatro strings. Valida os
registradores das propriedades de brilho/lux e as constantes numéricas, esvazia
somente os dois defaults e os textos diagnósticos correspondentes. Não altera
.locals, desvios, strings iguais em outros métodos ou o restante da lógica.
Rejeita fluxos ambíguos/alterados e não grava parcialmente. O legado só é
removido depois de instalada a substituição, na mesma condição de execução.
A adaptação ainda precisa passar contra o doador real; os testes são sintéticos.

Foram obtidos e conferidos pelo Git blob ID 170 arquivos de texto upstream para
esta revisão (scripts, módulos e patches), incluindo os 66 patches da base
relevantes às árvores unica/exynos9820/beyond1lte. O inventário completo por
patch está em manifests/legacy-patch-review.json, incluindo diretórios dex fixos,
registradores, lambdas sintéticas e dependências de desvios/catch. Inclui patches
condicionais: estar no inventário NÃO significa estar ativo nesse doador.
Isso expõe, por exemplo, a fragilidade de deknox/assinatura/cutout/telecom sem
converter cegamente alterações complexas ou desativar módulos para passar.
Os scripts HEX nativos também estão inventariados; padrões binários, toolchain,
montagem de imagens e comportamento em hardware não foram certificados.

A verificação agora não depende de reenviar um build completo para descobrir
somente o próximo hunk. Antes da passagem de produção, integration/build.py
executa uma passagem DIAGNÓSTICA dos módulos na ordem e condições originais:

* mantém --check + aplicação atômica dos patches válidos, respeitando a sequência;
* acumula hunks incompatíveis e continua a inspeção dos demais patches/módulos;
* cada módulo roda em um processo separado com errexit: falha de customize/HEX
  não é escondida e não impede inspecionar os módulos posteriores;
* módulos que falham cedo ficam explicitamente com cobertura incompleta;
* registra conclusão das quatro árvores existentes e recusa travessia vazia,
  incompleta ou duplicada; o escopo é dos caminhos condicionais executados;
* adia o kernel e termina antes de montar APKs/JARs/imagens ou criar ZIP;
* qualquer falha bloqueia a passagem real, retirement e empacotamento;
* se tudo passar, --force reconstrói work_dir a partir das firmwares ainda
  retidas, limpa os APKs decodificados e reaplica os patches com os erros fatais
  originais. Alterações de diagnóstico não viram ROM por engano.

Relatórios: out/beyoud-logs/patch-preflight.{json,jsonl}, logs por módulo e até
16 MiB de smali real dos alvos incompatíveis no artefato de diagnóstico. Uma
falha anterior pode causar rejeições dependentes; não tratar a contagem como
número de bugs independentes. Falhas na preparação da árvore, anteriores aos
módulos, continuam fatais e não permitem afirmar cobertura completa.

Também corrigido o wait múltiplo no overlay APKTool: cada PID é aguardado e os
DEX ficam limitados a THREAD_COUNT/BEYOUD_JOBS, em vez de lançar todos juntos e
aceitar só o resultado do último. Esta revisão não promete boot nem ausência de
outros erros. A workspace do runner encerrado continua irrecuperável e uma nova
verificação do doador ainda exige preparar as firmwares outra vez.
